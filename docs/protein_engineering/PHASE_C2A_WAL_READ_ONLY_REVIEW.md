# C.2A-D1 SQLite 日志与只读适配独立设计审查

## 2026-11-14：P1-B 定向修复后的现行边界

现行策略：`ISOLATED_LOCKED_ROLLBACK_COPY_V1`。
旧的“检查头后在原件上 mode=ro 连接”不再用于 Desktop C.2A。
领域 `load_rate_records` 本身没有改变，Desktop 仅将已验证私有副本交给它；
独立调用旧领域 API 直接读取原件不能继承本策略的安全保证。

### 设计门槛与方案比较

| 方案 | 评估 | 决定 |
|---|---|---|
| A 原件 OS 锁 + 直接 SQLite | Windows sharing 可阻止写/删除，POSIX 是协作锁；SQLite 对源目录的共享内存/日志行为仍须控制 | 不在原件建立 SQLite 连接 |
| B 原件受保护字节采集 + 私有副本 | 全量 hash/身份核验，可将 SQLite 日志行为限制在临时目录；增加三次源读取、完整副本复读及磁盘空间 | 本轮选择 |
| C 仅要求用户离线静止 | 不能靠确认框排除检查后切换日志的竞态 | 不能单独作为安全依据 |

设计门槛先于应用接入完成。原型 8 项测试通过，证据和比较表位于
`dist/protein-engineering/c2a-desktop-d1-fixes-20261114/SQLITE_DESIGN_GATE.md`。
本轮由用户明确授权在门槛通过后实施，不需要绕过来源校验或改 SQLite v3。

### 实际来源链

1. 解析现存本地路径，以 lstat 核验任一 WAL/SHM/journal；存在或元数据权限异常均拒绝，不恢复、不删除。
2. Windows 以 GENERIC_READ / FILE_SHARE_READ 打开原件，采集期间不允许写/删除共享；
   POSIX 对 SQLite 的 pending/reserved/shared 锁字节加共享锁。
3. 使用同一只读句柄核对 fstat 与路径的 dev/inode，拒绝非普通文件及身份不一致。
4. 检查 SQLite magic 与 1/1 rollback 头，拒绝 WAL 2/2，不遗漏其已提交事务。
5. 在锁定期间分别计算原件完整 hash、复制流 hash、关闭后副本完整 hash、原件再次完整 hash；
   同时复核 size、mtime、ctime、文件身份与 sidecar 状态，全部匹配才接受采集。
6. 原件句柄释放后，SQLite 只打开私有副本（mode=ro/query_only）。
   检查 v3、quick_check，再由原领域适配器验证迁移史、来源字节、C.1 回放及标定。
7. 发布记录前再次验证私有副本完整 hash；重新受保护读取原件核对身份、完整 hash 和日志状态。
   任何来源变化拒绝发布，不以“最后返回错误”冒充无副作用。

审核对象另绑定文件身份和原件 hash；即使相同字节换成另一文件，Desktop 旧审核也会失效。
报告外层记录来源策略、原件 hash 和所提供的身份 token；原 C.2A 输入/结果摘要不变。
临时副本不是原始实验记录，不写回 SQLite，不公开、不上传、不自动保留。

### 私有目录、清理和权限

临时目录使用 0700；Windows 要求 Python 已支持此 ACL 语义
（3.10.15+、3.11.10+、3.12.4+ 或 3.13+），旧版本明确拒绝而不是降低权限。
测试使用隔离 RUNNER_TEMP，源码使用用户 LOCALAPPDATA 下的私有区域。
所有副本连接显式关闭；成功或异常后清理本次副本，不操作源 sidecar。
副本只需关闭后字节可读且完整复核，不承诺断电持久性；报告发布仍保留 fsync。
清理失败会成为错误；不将残留副本当成功报告，也不回退到原件 SQLite 连接。

### 实测与归因

23 项正式来源测试全部通过，并保存可观察访问轨迹：
`dist/protein-engineering/c2a-desktop-d1-fixes-20261114/source-access-trace.json`。
新增原生 open 审计事件测试，拒绝发生在实际原件打开前。
33 次 SQLite 打开中，26 次只读 URI 全部指向 `protein-mm-private-` 副本，
对原件的 SQLite 打开为测试显式故障写入者，程序自身只读原件 URI 次数为 0。

覆盖静止库、三种 sidecar、关闭 WAL、锁/权限、外部进程在采集锁中尝试进入 WAL、
复制时修改、复制后截断/修改/替换、私有副本清理和校验损坏。
外部进程可在采集后写入并提交 WAL，持有连接等待验证；测试比较写入者完成后的
WAL/SHM hash 与读取后状态，证明读取方未修改、创建或删除其 sidecar，并明确拒绝结果。
不是要求外部写入者不产生它自己的日志。

### 限制及审核结论

本机实际测试是 Windows；没有可用的 WSL Linux 环境，不能声称 Linux 实测通过。
POSIX 字节锁对合作 SQLite 进程有效，不能阻止任意非协作原始写；完整 hash/身份/ctime
复核用于检测变化，不宣称可以认证对手故意恢复全部字节与元数据的情形。
不支持的平台、锁策略、权限或来源资格应拒绝，不转为不安全直接读取。
不承诺远程/特殊 VFS、恶意内核或损坏硬件的安全性，SHA256 不是外部真实性认证。

P1-B 在本轮 Desktop / 普通本地来源合同内已消除。
ADAPTER_CONTRACT_CHANGED：NO；SOURCE_SQLITE_CONNECTIONS：0（应用读取方）；SQLITE_SCHEMA：v3。
冻结包仍无 SciPy；发布依赖和跨平台 CI 是后续独立验收，不在本轮发布。

设计依据：[Microsoft CreateFile](https://learn.microsoft.com/windows/win32/api/fileapi/nf-fileapi-createfilea)、
[SQLite 文件锁](https://www.sqlite.org/lockingv3.html)、
[Python Windows 0700 目录语义](https://docs.python.org/3.10/library/os.html)。

## 以下为 2026-11-13 原始设计审查记录（历史，现行策略以上节为准）

日期：2026-11-13（Asia/Shanghai）。范围：日志边界复现与设计，不修改 C.2A 领域适配器。

## 1. 复现与结论

使用 `tests/test_mm_kinetics.py` 的全合成 v3 fixture，含 7 个已保存 C.1 分析。
在隔离目录中显式设置 `PRAGMA journal_mode=WAL`，关闭测试写连接。
此时数据库头第 18、19 字节均为 2，且没有现存 `-wal/-shm`。
原 `load_rate_records(path, ids)` 的 `mode=ro` 连接读取成功，返回 7 条记录，
但创建了空的 `-wal` 和 32768 字节 `-shm`。
数据库主体 SHA256 和 mtime 不变，文件集合改变。

证据位于本地忽略目录：
`dist/protein-engineering/c2a-desktop-d1-20261113/wal-review/closed-wal-existing-adapter.json`。
原复现未改写、删除或当作正常只读通过；SAFE_CI boundary violations=0。
测试仅访问合成库，没有打开真实用户数据库。

**审查结论：WAL 来源的“完全不创建文件”保证尚不成立，属于 WAL 支持的阻断项。**
已有边车检查不足以拒绝关闭后的 WAL 格式库；SQLite 的 `mode=ro` 不等于不创建共享内存文件。
本轮不修改 `protein_engineering/mm_rate_adapter.py`，不将此问题修成未经审核的新适配器合同。

## 2. 本轮 Desktop 的保守边界

新增应用层 `desktop/protein_mm.py` 在刷新、来源核验、拟合、导出路径采用同一入口：

1. 必须是明确选择的现存本地库，不创建或迁移。
2. 打开 SQLite 前拒绝任意现存 `-journal/-wal/-shm`。
3. 只用二进制文件读取检查 SQLite magic 和日志头字节。
   仅允许头字节 1/1 的标准 rollback-journal 格式；WAL 2/2 和未知格式拒绝。
4. 连接设置 `mode=ro`、`query_only=ON`、显式读事务；核对 application_id 和 v3。
   读取 schema 固定普通读快照，并再次检查日志边界。
5. 目录列表复用 C.1 的 `RateStorage.initial_rate_records()`，仅替换为只读连接，
   不构造会迁移的 `ProteinStore`；目录中的信息只作“待核验”展示。
6. 真实拟合输入仍只来自原 `load_rate_records(path, analysis_ids)`，
   保留其迁移史、源字节 SHA256、观测/身份链接、标定和 C.1 回放检查。
   目录读取不能生成可绕过审核的 `RateRecord`。

额外限制没有放松领域适配器的任何条件，不是重新实现数据来源校验。
正常默认 DELETE 模式下，同一 Desktop 导入、保存 C.1 后的 C.2A 路径已通过合成测试。
活动 WAL、关闭后无边车的 WAL、孤立 SHM/journal 都拒绝。
不自动 checkpoint、不删除边车、不切换 journal_mode、不复制或修复用户数据库。

## 3. 未来适配器合同变更候选，尚未实施

最小候选是让领域适配器也在连接前检查日志头并明确拒绝 WAL 格式。
这会收紧原先可能接受的输入，应独立审查兼容性、平台行为、错误类型及回归，
不能仅因 Desktop 新增 guard 就宣称领域 API 已修复。

如将来需要真正支持 WAL，必须另审：

- 写入者停用和 checkpoint 的责任、证据及用户授权。
- 一致性快照获取方式；不允许在活动 WAL 上只复制主文件。
- 热 journal、锁、共享内存和读取权限的跨平台行为。
- 快照包含完整未丢失事务的证明、源文件集合与内容摘要。
- `immutable=1` 的前提；不能用它强行忽略未合并 WAL 或掩盖损坏。
- 读前/读后来源一致性和故障恢复；不能自动删日志来获得通过。

## 4. 限制与验收

当前应用只支持经过核验的、无并发写入的普通本地 v3 库。
读事务、字节摘要和动作前重核用于一致性审计，不是恶意文件替换防护、全文件系统沙箱或真实性认证。
外部写入/日志模式切换与连接之间的任意竞态没有获得 WAL 安全支持承诺。
来源发生变化时拒绝旧审核；用户需要重新核验，不能绕过核心资格。

正式测试覆盖刷新和核验对 2/2 头的拒绝、三类现存边车的保留、活动 WAL、
源字节损坏、库变化、原适配器资格及普通同会话导入→C.1→C.2A。
均检查合成源库字节与边车状态；不将已拒绝 WAL 的测试宣称为 WAL 可用性验收。

WAL_SUPPORT：BLOCKED_PENDING_ADAPTER_REVIEW。
DEFAULT_ROLLBACK_DESKTOP_WORKFLOW：PASS（合成环境）。
ADAPTER_CONTRACT_CHANGED：NO。
SQLITE_SCHEMA_CHANGED：NO（仍为 v3）。
