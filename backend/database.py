import sqlite3
import json
import os
from datetime import datetime

DATABASE_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'log_analysis.db')

def get_db():
    """获取数据库连接，自动创建目录和表"""
    os.makedirs(os.path.dirname(DATABASE_PATH), exist_ok=True)
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")  # 提升并发性能
    return conn

def init_db():
    """初始化所有数据表"""
    conn = get_db()
    c = conn.cursor()
    # 遥测数据表：替代 telemetry_cache.json
    c.execute('''CREATE TABLE IF NOT EXISTS telemetry (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        machine_id TEXT NOT NULL UNIQUE,
        timestamp TEXT NOT NULL,
        status TEXT DEFAULT 'unknown',
        machine_state TEXT DEFAULT 'IDLE',
        current_step TEXT DEFAULT '',
        current_sn TEXT DEFAULT '',
        model TEXT DEFAULT '',
        test_mode TEXT DEFAULT '',
        station TEXT DEFAULT 'FCT',
        payload_json TEXT,  -- 完整机台 payload JSON，包含 measurements / alarms / instruments 等
        online INTEGER DEFAULT 1,
        last_heartbeat TEXT
    )''')
    # 日志文件元数据
    c.execute('''CREATE TABLE IF NOT EXISTS log_files (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        filename TEXT UNIQUE NOT NULL,
        sn TEXT,
        test_station TEXT,
        start_time TEXT,
        end_time TEXT,
        overall_status TEXT,  -- PASS/FAIL/INTERRUPTED/PARSE_ERROR
        raw_data TEXT,        -- 原始文件内容（可选，轻量级场景可存）
        parsed_at TEXT
    )''')
    # 单个测试项明细
    c.execute('''CREATE TABLE IF NOT EXISTS test_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        log_id INTEGER NOT NULL,
        test_name TEXT,
        result TEXT,  -- PASS/FAIL
        value REAL,
        unit TEXT,
        lower_limit REAL,
        upper_limit REAL,
        FOREIGN KEY (log_id) REFERENCES log_files(id) ON DELETE CASCADE
    )''')
    # TOP FAIL 统计缓存（每小时汇总一次，避免实时全表扫描）
    c.execute('''CREATE TABLE IF NOT EXISTS fail_statistics (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        stat_date TEXT NOT NULL,
        fail_item TEXT NOT NULL,
        count INTEGER DEFAULT 0,
        station TEXT,
        last_updated TEXT
    )''')
    conn.commit()
    conn.close()

def save_telemetry(machine_id, data):
    """保存或更新一条机台遥测记录 — 保存完整 payload，与 app.py normalize_machine_payload 对齐"""
    conn = get_db()
    c = conn.cursor()
    now = datetime.now().isoformat()
    # 将完整 payload 序列化存储，后续可从 DB 还原完整机台状态
    payload_json = json.dumps(data, ensure_ascii=False) if isinstance(data, dict) else json.dumps({})
    c.execute("SELECT id FROM telemetry WHERE machine_id=?", (machine_id,))
    row = c.fetchone()
    if row:
        c.execute('''UPDATE telemetry SET
                        timestamp=?, status=?, machine_state=?, current_step=?,
                        current_sn=?, model=?, test_mode=?, station=?,
                        payload_json=?, online=1, last_heartbeat=?
                     WHERE machine_id=?''',
                  (now,
                   data.get('machine_state', data.get('status', 'unknown')),
                   data.get('machine_state', 'IDLE'),
                   data.get('current_step', ''),
                   data.get('current_sn', ''),
                   data.get('model', ''),
                   data.get('test_mode', ''),
                   data.get('station', 'FCT'),
                   payload_json,
                   now,
                   machine_id))
    else:
        c.execute('''INSERT INTO telemetry
                     (machine_id, timestamp, status, machine_state, current_step,
                      current_sn, model, test_mode, station, payload_json, online, last_heartbeat)
                     VALUES (?,?,?,?,?,?,?,?,?,?,1,?)''',
                  (machine_id, now,
                   data.get('machine_state', data.get('status', 'unknown')),
                   data.get('machine_state', 'IDLE'),
                   data.get('current_step', ''),
                   data.get('current_sn', ''),
                   data.get('model', ''),
                   data.get('test_mode', ''),
                   data.get('station', 'FCT'),
                   payload_json,
                   now))
    conn.commit()
    conn.close()

def get_all_telemetry():
    """获取所有在线机台最新遥测 — 返回 app.py summarize_machine 所需字段"""
    conn = get_db()
    rows = conn.execute("SELECT * FROM telemetry WHERE online=1").fetchall()
    conn.close()
    result = []
    for row in rows:
        payload = {}
        try:
            if row['payload_json']:
                payload = json.loads(row['payload_json'])
        except Exception:
            pass
        result.append({
            'machine_id': row['machine_id'],
            'timestamp': row['timestamp'],
            'machine_state': row['machine_state'],
            'current_step': row['current_step'],
            'current_sn': row['current_sn'],
            'model': row['model'],
            'test_mode': row['test_mode'],
            'station': row['station'],
            'measurements': payload.get('measurements', {}),
            'alarms': payload.get('alarms', []),
            'instruments': payload.get('instruments', {}),
            'online': bool(row['online']),
            'last_heartbeat': row['last_heartbeat'],
        })
    return result

def get_telemetry_summary():
    """从 DB 构建机台遥测摘要（与 app.py build_machine_summary 语义对齐）"""
    machines = get_all_telemetry()
    now_ts = datetime.now().timestamp()
    ONLINE_SECONDS = 5
    STALE_SECONDS = 30

    online_count = 0
    stale_count = 0

    for m in machines:
        try:
            hb_ts = datetime.fromisoformat(m['last_heartbeat']).timestamp()
        except Exception:
            hb_ts = 0
        age = now_ts - hb_ts
        if age <= ONLINE_SECONDS:
            status = 'ONLINE'
            online_count += 1
        elif age <= STALE_SECONDS:
            status = 'STALE'
            stale_count += 1
        else:
            status = 'OFFLINE'

        alarm_count = len(m.get('alarms', []) or [])
        display_state = 'WARNING' if alarm_count > 0 else m.get('machine_state', 'IDLE')
        if status != 'ONLINE':
            display_state = status

        m['online_status'] = status
        m['display_state'] = display_state
        m['alarm_count'] = alarm_count

    machines.sort(key=lambda x: x['machine_id'])
    total = len(machines)
    offline_count = total - online_count - stale_count
    return {
        'total': total,
        'online': online_count,
        'stale': stale_count,
        'offline': offline_count,
        'machines': machines
    }

def mark_telemetry_offline(timeout_seconds=60):
    """将超时未心跳的机台标记为离线"""
    conn = get_db()
    now = datetime.now()
    threshold = now.timestamp() - timeout_seconds
    conn.execute("UPDATE telemetry SET online=0 WHERE last_heartbeat < ?", 
                 (datetime.fromtimestamp(threshold).isoformat(),))
    conn.commit()
    conn.close()

# ============================================================
# [新增] 批量日志入库 — 将 fct_parser 解析结果同步到 DB
# ============================================================

def save_log_records_batch(records):
    """批量将 parse_fct_xml 的输出 records 存入 log_files + test_items 表。
    每个 record 对应一条 log_files 行；record['raw_items'] 展开为 test_items。
    返回 (new_count, skip_count)。
    """
    conn = get_db()
    c = conn.cursor()
    new_count = 0
    skip_count = 0
    parsed_at = datetime.now().isoformat()

    for record in records:
        filename = record.get('source_file', '')
        if not filename:
            skip_count += 1
            continue

        # 检查是否已存在
        existing = c.execute("SELECT id FROM log_files WHERE filename=?", (filename,)).fetchone()
        log_id = existing['id'] if existing else None

        sn = record.get('sn', '')
        station = record.get('station', 'FCT')
        start_time = record.get('dut_time') or record.get('panel_time') or record.get('batch_time') or record.get('time', '')
        end_time = record.get('time', '')
        overall_status = record.get('business_result', '中断')

        if log_id:
            # 更新已有记录
            c.execute('''UPDATE log_files SET sn=?, test_station=?, start_time=?, end_time=?,
                         overall_status=?, parsed_at=? WHERE id=?''',
                      (sn, station, start_time, end_time, overall_status, parsed_at, log_id))
            # 删除旧 test_items 重插（幂等）
            c.execute("DELETE FROM test_items WHERE log_id=?", (log_id,))
            skip_count += 1
        else:
            c.execute('''INSERT INTO log_files (filename, sn, test_station, start_time, end_time, overall_status, parsed_at)
                         VALUES (?,?,?,?,?,?,?)''',
                      (filename, sn, station, start_time, end_time, overall_status, parsed_at))
            log_id = c.lastrowid
            new_count += 1

        # 写入测试项明细
        raw_items = record.get('raw_items', []) or []
        for item in raw_items:
            val = None
            try:
                val = float(item.get('value', ''))
            except Exception:
                pass
            lo = None
            try:
                lo = float(item.get('lolim', ''))
            except Exception:
                pass
            hi = None
            try:
                hi = float(item.get('hilim', ''))
            except Exception:
                pass
            c.execute('''INSERT INTO test_items (log_id, test_name, result, value, unit, lower_limit, upper_limit)
                         VALUES (?,?,?,?,?,?,?)''',
                      (log_id,
                       item.get('name') or item.get('raw_name', ''),
                       item.get('business_status') or item.get('result', '中断'),
                       val,
                       item.get('unit', ''),
                       lo,
                       hi))
    conn.commit()
    conn.close()
    return new_count, skip_count


# ============================================================
# [原] 单条日志保存（保留，供日后其他场景使用）
# ============================================================
def save_log_record(filename, sn, test_station, start_time, end_time, overall_status, raw_data=""):
    """保存日志文件解析结果，返回 log_id"""
    conn = get_db()
    c = conn.cursor()
    c.execute('''INSERT OR REPLACE INTO log_files (filename, sn, test_station, start_time, end_time, overall_status, raw_data, parsed_at)
                 VALUES (?,?,?,?,?,?,?,?)''',
              (filename, sn, test_station, start_time, end_time, overall_status, raw_data, datetime.now().isoformat()))
    log_id = c.lastrowid
    conn.commit()
    conn.close()
    return log_id

def save_test_items(log_id, items):
    """批量保存测试项明细"""
    conn = get_db()
    c = conn.cursor()
    for item in items:
        c.execute('''INSERT INTO test_items (log_id, test_name, result, value, unit, lower_limit, upper_limit)
                     VALUES (?,?,?,?,?,?,?)''',
                  (log_id, item.get('name'), item.get('result'),
                   item.get('value'), item.get('unit'),
                   item.get('lower'), item.get('upper')))
    conn.commit()
    conn.close()

def get_logs_by_sn(sn_suffix):
    """根据SN后缀查询日志"""
    conn = get_db()
    rows = conn.execute("SELECT * FROM log_files WHERE sn LIKE ? ORDER BY parsed_at DESC", (f'%{sn_suffix}%',)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_log_detail(log_id):
    """获取日志详情及所有测试项"""
    conn = get_db()
    log = conn.execute("SELECT * FROM log_files WHERE id=?", (log_id,)).fetchone()
    if not log:
        conn.close()
        return None
    items = conn.execute("SELECT * FROM test_items WHERE log_id=?", (log_id,)).fetchall()
    conn.close()
    result = dict(log)
    result['items'] = [dict(item) for item in items]
    return result

def get_top_fail(station=None, limit=10):
    """从统计表获取TOP FAIL，若为空则回退实时查询 test_items"""
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM fail_statistics")
    stat_count = c.fetchone()[0]
    if stat_count > 0:
        query = "SELECT fail_item, SUM(count) as total FROM fail_statistics"
        params = []
        if station:
            query += " WHERE station=?"
            params.append(station)
        query += " GROUP BY fail_item ORDER BY total DESC LIMIT ?"
        params.append(limit)
        rows = c.execute(query, params).fetchall()
        conn.close()
        return [{'fail_item': row['fail_item'], 'count': row['total']} for row in rows]
    else:
        # 实时查询
        query = '''SELECT ti.test_name as fail_item, COUNT(*) as count
                   FROM test_items ti
                   JOIN log_files lf ON ti.log_id = lf.id
                   WHERE ti.result = 'FAIL' '''
        params = []
        if station:
            query += " AND lf.test_station = ?"
            params.append(station)
        query += " GROUP BY ti.test_name ORDER BY count DESC LIMIT ?"
        params.append(limit)
        rows = c.execute(query, params).fetchall()
        conn.close()
        return [{'fail_item': row['fail_item'], 'count': row['count']} for row in rows]

def update_fail_statistics():
    """每日/每小时统计汇总（可被定时任务调用）"""
    conn = get_db()
    today = datetime.now().strftime('%Y-%m-%d')
    c = conn.cursor()
    # 先清理当日旧数据，防止重复插入导致计数膨胀
    c.execute("DELETE FROM fail_statistics WHERE stat_date = ?", (today,))
    c.execute('''INSERT INTO fail_statistics (stat_date, fail_item, count, station, last_updated)
                 SELECT date(lf.parsed_at), ti.test_name, COUNT(*), lf.test_station, datetime('now')
                 FROM test_items ti
                 JOIN log_files lf ON ti.log_id = lf.id
                 WHERE ti.result = 'FAIL' AND date(lf.parsed_at) = ?
                 GROUP BY date(lf.parsed_at), ti.test_name, lf.test_station''', (today,))
    conn.commit()
    conn.close()