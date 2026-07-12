# Java 诊断内置工具包

此目录随代码发布，供 Java 诊断在**离线/无外网**环境下把工具包 SFTP 推送到目标机使用。
优先级：**用户上传包 > 本目录内置包 > 目标机联网下载**。

## 已内置（随仓库分发）
- `arthas-boot.jar` — Arthas 启动器（阿里云官方，约 145KB）
- `async-profiler-linux-x64.tar.gz` — 火焰图采样器 async-profiler 3.0 linux-x64（约 275KB）

## JDK（需自行放置，体积过大不入库）
把一个 **目标机同架构** 的 Linux JDK/JRE 压缩包放到本目录并命名为：

```
jdk.tar.gz
```

放置后即成为「内置 JDK」，诊断时会推送到目标机 `/tmp/aiops-java-tools/` 解压使用，
使目标机即使没有安装 java 也能跑 Arthas / 火焰图。

- 架构要与目标机一致（x86_64 用 x64 包，aarch64 用 arm64 包），否则推过去无法执行。
- 建议用 JDK8 完整版（含 `lib/tools.jar`）或 JDK11+，解压后含 `bin/java` 即可。
- 例：`tar czf jdk.tar.gz -C /path/to jdk8u402`，再放到本目录。

## 更新内置的 Arthas / async-profiler
直接替换本目录同名文件即可（保持文件名不变）。
