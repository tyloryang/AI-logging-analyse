# Rocky Linux 9 配置静态 IP 和路由

> 来源：https://199604.com/3206

## 概述

Rocky Linux 9 的网络配置方式相较于 CentOS 7/8（及 Rocky Linux 8）发生了重大变化，从传统的 `ifcfg` 格式迁移到了 NetworkManager 的 **keyfile** 格式。

| 项目 | CentOS 7/8 / Rocky Linux 8 | Rocky Linux 9 |
|------|-----------------------------|----------------|
| 配置目录 | `/etc/sysconfig/network-scripts/` | `/etc/NetworkManager/system-connections/` |
| 文件格式 | ifcfg 格式（`ifcfg-ens33`） | keyfile 格式（`ens33.nmconnection`） |
| ifcfg 格式支持 | 原生支持，有模板 | 仍可用，但不再提供模板 |

---

## 配置步骤

### 1. 进入配置目录并备份

```bash
cd /etc/NetworkManager/system-connections
ls -l

# 备份原始配置（操作前必做）
cp ens33.nmconnection ens33.nmconnection.bak
```

### 2. 编辑网卡配置文件

编辑 `ens33.nmconnection`（文件名与网卡名对应）。

**修改前（DHCP 自动获取）：**

```ini
[ipv4]
method=auto
```

**修改后（静态 IP）：**

```ini
[connection]
id=ens33
uuid=cccfabd7-6306-38dd-91c9-219651ea0f08
type=ethernet
interface-name=ens33

[ethernet]

[ipv4]
method=manual
address1=192.168.100.136/24
gateway=192.168.100.2
route1=192.168.100.2
dns=114.114.114.114;8.8.8.8

[ipv6]
addr-gen-mode=eui64
method=auto
```

**关键字段说明：**

| 字段 | 说明 |
|------|------|
| `method=manual` | 启用静态 IP 模式（改为 `auto` 则恢复 DHCP） |
| `address1=IP/掩码` | 第一个 IP 地址，多 IP 依次用 `address2`、`address3` 追加 |
| `gateway` | 默认网关 |
| `route1` | 静态路由条目（可追加 `route2`、`route3`） |
| `dns` | DNS 服务器，多个用 `;` 分隔 |

### 3. 应用配置

```bash
# 重新加载连接配置
nmcli c reload ens33

# 激活连接
nmcli c up ens33
```

---

## 验证配置

### 查看所有连接状态

```bash
nmcli c show
```

### 查看指定网卡详细信息

```bash
nmcli device show ens33
```

预期输出中的路由信息示例：

```
IP4.ROUTE[1]:    dst = 192.168.100.0/24, nh = 0.0.0.0, mt = 100
IP4.ROUTE[2]:    dst = 192.168.100.0/24, nh = 0.0.0.0, mt = 100
IP4.ROUTE[3]:    dst = 0.0.0.0/0, nh = 192.168.100.2, mt = 100
```

- `ROUTE[1/2]`：局域网段路由（下一跳为 `0.0.0.0` 表示直连）
- `ROUTE[3]`：默认路由（`0.0.0.0/0`，下一跳为网关 `192.168.100.2`）

---

## 常见问题

**Q：修改配置后 IP 没有生效？**

执行 `nmcli c reload ens33` 后，还需要 `nmcli c up ens33` 激活连接，两步缺一不可。

**Q：旧的 ifcfg 格式文件还能用吗？**

可以，Rocky Linux 9 仍支持读取 `/etc/sysconfig/network-scripts/ifcfg-*` 格式，但官方不再为新安装的系统提供模板，推荐使用 keyfile 格式。

**Q：如何配置多个 IP 地址？**

在 `[ipv4]` 段依次追加：

```ini
address1=192.168.100.136/24
address2=192.168.100.137/24
address3=10.0.0.10/8
```

---

## 参考资料

- [Rocky Linux 官方文档](https://docs.rockylinux.org/)
- [NetworkManager keyfile 格式说明](https://networkmanager.dev/docs/api/latest/nm-settings-keyfile.html)
- 原文：https://199604.com/3206
