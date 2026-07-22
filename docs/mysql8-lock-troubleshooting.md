# MySQL 8 锁表与锁等待排查指南

本文用于排查 MySQL 8 中常见的行锁等待、事务阻塞、元数据锁和死锁问题。

> MySQL 8 已移除旧的 `information_schema.INNODB_LOCKS` 和 `INNODB_LOCK_WAITS`。应使用 `sys` Schema、`performance_schema` 和 `information_schema.innodb_trx`。

## 一、快速判断谁阻塞了谁

优先执行下面的查询：

```sql
SELECT
    waiting_trx_id,
    waiting_pid,
    waiting_query,
    blocking_trx_id,
    blocking_pid,
    blocking_query
FROM sys.innodb_lock_waits;
```

在 MySQL 命令行中，可以使用纵向格式查看全部字段：

```sql
SELECT *
FROM sys.innodb_lock_waits\G
```

重点字段：

| 字段 | 含义 |
| --- | --- |
| `waiting_pid` | 正在等待锁的连接 ID |
| `waiting_query` | 被阻塞的 SQL |
| `blocking_pid` | 持有锁并造成阻塞的连接 ID |
| `blocking_query` | 阻塞其他事务的 SQL |
| `locked_table` | 被锁定的表 |
| `locked_index` | 涉及的索引 |

如果查询结果为空，说明当前时刻没有发生 InnoDB 锁等待，但不代表数据库中没有事务持有锁。

## 二、查看当前持有和等待的数据锁

```sql
SELECT
    ENGINE_TRANSACTION_ID,
    OBJECT_SCHEMA,
    OBJECT_NAME,
    INDEX_NAME,
    LOCK_TYPE,
    LOCK_MODE,
    LOCK_STATUS,
    LOCK_DATA
FROM performance_schema.data_locks
ORDER BY OBJECT_SCHEMA, OBJECT_NAME;
```

字段说明：

| 字段值 | 含义 |
| --- | --- |
| `LOCK_TYPE = RECORD` | 记录锁或行锁 |
| `LOCK_TYPE = TABLE` | 表级锁或表级意向锁 |
| `LOCK_MODE = X` | 排他锁 |
| `LOCK_MODE = S` | 共享锁 |
| `LOCK_STATUS = WAITING` | 正在等待锁 |
| `LOCK_STATUS = GRANTED` | 已经获得锁 |

只查看正在等待的锁：

```sql
SELECT *
FROM performance_schema.data_locks
WHERE LOCK_STATUS = 'WAITING';
```

## 三、查看等待事务与阻塞事务的完整关系

```sql
SELECT
    r.trx_id AS waiting_trx_id,
    r.trx_mysql_thread_id AS waiting_pid,
    r.trx_query AS waiting_query,
    b.trx_id AS blocking_trx_id,
    b.trx_mysql_thread_id AS blocking_pid,
    b.trx_query AS blocking_query
FROM performance_schema.data_lock_waits w
JOIN information_schema.innodb_trx r
    ON r.trx_id = w.requesting_engine_transaction_id
JOIN information_schema.innodb_trx b
    ON b.trx_id = w.blocking_engine_transaction_id;
```

该查询适合明确以下问题：

1. 哪个事务正在等待锁。
2. 哪个事务持有冲突锁。
3. 两个事务分别属于哪个数据库连接。
4. 等待方和阻塞方正在执行什么 SQL。

## 四、排查元数据锁

如果 `ALTER TABLE`、`DROP TABLE`、`TRUNCATE TABLE`、创建索引等 DDL 操作一直卡住，应重点检查元数据锁：

```sql
SELECT
    object_schema,
    object_name,
    waiting_pid,
    waiting_query,
    waiting_query_secs,
    blocking_pid,
    blocking_account,
    sql_kill_blocking_connection
FROM sys.schema_table_lock_waits\G
```

如果连接状态出现以下内容，通常说明正在等待元数据锁：

```text
Waiting for table metadata lock
```

常见原因是某个连接开启事务并访问了目标表，但长时间没有执行 `COMMIT` 或 `ROLLBACK`。

## 五、查看当前连接和未完成事务

查看全部数据库连接及其当前 SQL：

```sql
SHOW FULL PROCESSLIST;
```

查看当前 InnoDB 事务：

```sql
SELECT
    trx_id,
    trx_state,
    trx_started,
    TIMESTAMPDIFF(SECOND, trx_started, NOW()) AS trx_age_seconds,
    trx_mysql_thread_id,
    trx_rows_locked,
    trx_rows_modified,
    trx_query
FROM information_schema.innodb_trx
ORDER BY trx_started;
```

重点检查：

- 持续时间异常长的事务。
- 锁定大量记录的事务。
- 修改大量记录但迟迟未提交的事务。
- `trx_query` 为空，但事务依然存在的空闲连接。

`trx_query` 为空不代表事务已经结束。连接可能在执行完 SQL 后进入空闲状态，但仍未提交事务并继续持有锁。

## 六、安全解除阻塞

### 1. 优先正常结束事务

如果能够操作阻塞连接，应在该连接中执行：

```sql
COMMIT;
```

或者：

```sql
ROLLBACK;
```

### 2. 紧急终止阻塞连接

确认 `blocking_pid` 后，可以执行：

```sql
KILL CONNECTION 12345;
```

将 `12345` 替换为真实的阻塞连接 ID。

> 执行 `KILL CONNECTION` 会中断连接并回滚其未提交事务。数据量较大时，回滚可能需要一段时间，锁通常要等到回滚完成后才会释放。

谨慎使用：

```sql
KILL QUERY 12345;
```

`KILL QUERY` 只终止当前语句，连接中的事务可能仍然处于未提交状态，因此锁可能不会释放。

## 七、排查死锁

查看最近一次 InnoDB 死锁：

```sql
SHOW ENGINE INNODB STATUS\G
```

在结果中搜索：

```text
LATEST DETECTED DEADLOCK
```

需要长期记录所有死锁时，可评估启用：

```sql
SET GLOBAL innodb_print_all_deadlocks = ON;
```

启用后，死锁信息会写入 MySQL 错误日志。该设置会影响全局运行状态，生产环境应先确认日志量和变更规范。

## 八、推荐排查顺序

1. 执行 `SELECT * FROM sys.innodb_lock_waits`，确认等待方和阻塞方。
2. 执行 `SELECT * FROM sys.schema_table_lock_waits`，排除元数据锁。
3. 查询 `information_schema.innodb_trx`，寻找长事务和空闲未提交事务。
4. 使用 `SHOW FULL PROCESSLIST` 确认连接来源和运行状态。
5. 联系业务方正常提交或回滚阻塞事务。
6. 只有在确认业务影响后，才执行 `KILL CONNECTION`。
7. 如果锁等待已经消失但怀疑发生过死锁，检查 `SHOW ENGINE INNODB STATUS`。

## 九、常见原因与处理建议

| 现象 | 常见原因 | 建议 |
| --- | --- | --- |
| 更新语句长时间等待 | 其他事务修改了相同行且未提交 | 找到 `blocking_pid`，提交或回滚阻塞事务 |
| DDL 一直卡住 | 存在未释放的元数据锁 | 查询 `sys.schema_table_lock_waits` |
| 阻塞 SQL 显示为空 | 持锁连接执行完 SQL 后处于空闲状态 | 查询 `innodb_trx`，检查未提交事务 |
| 批量更新锁很多行 | 事务范围过大或缺少有效索引 | 分批提交并检查执行计划和索引 |
| 间歇性报死锁 | 多个事务访问资源的顺序不一致 | 统一访问顺序、缩短事务并增加重试 |
| 杀掉 SQL 后仍未解锁 | 只执行了 `KILL QUERY`，事务仍存在 | 正常回滚或执行 `KILL CONNECTION` |

## 十、参考文档

- [MySQL 8.0：InnoDB 锁等待查询示例](https://dev.mysql.com/doc/refman/8.0/en/innodb-information-schema-examples.html)
- [MySQL 8.0：performance_schema.data_locks](https://dev.mysql.com/doc/refman/8.0/en/performance-schema-data-locks-table.html)
- [MySQL 8.0：performance_schema.data_lock_waits](https://dev.mysql.com/doc/refman/8.0/en/performance-schema-data-lock-waits-table.html)
- [MySQL 8.0：sys.schema_table_lock_waits](https://dev.mysql.com/doc/refman/8.0/en/sys-schema-table-lock-waits.html)
