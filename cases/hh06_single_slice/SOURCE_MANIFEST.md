# ANCF 源码与二进制清单

已将项目中的通用 C++ ANCF worker 快照放在本算例根目录，便于审计：

| 文件 | 来源 | SHA256（来源快照） | 说明 |
|---|---|---|---|
| `ancf_kernel.cpp` | `feature/ancf-spanwise-hydro-matrix-v1@355640e11925b9feddd1a52bb3d93596e5ee8251` | `6DDE195A8EA27F253A21D4A859BF41A620697963AB0A834BB9D982B51863AC06` | 含分段附加质量/线性阻尼接口的 kernel 源码 |
| `ancf_kernel.hpp` | 同上 | `C1182AB921D5517C2A5282F8B5FE51C3AB298BEC8B6015BFDCDBCA733C17E22C` | kernel 头文件 |
| `ancf_worker_main.cpp` | 同上 | `83F2D643F855894C8E74AAA11D0C76684E74886FFA0CCFA044B9FB368367DEB9` | worker IPC 主程序 |
| `cfd_ancf_ancf_kernel_worker` | `CFD_ANCF_VIV/runtime/292_cpp_worker_linux_build_v1/cfd_ancf_ancf_kernel_worker` | `7B246C53F2040CE9DCBA3100700E1D5DEF905E84D8452F560B6D1B29E88D8473` | Linux ELF worker（需确认与该源码提交的 ABI 一致） |

## 重要限制

上述 worker 是项目通用/接口验证构建，不等于已经确认的高 Re 单切片生产 participant。当前目录仍缺少与 200 个 CFD 圆柱面中心、13.12 m 高 Re 结构合同和 30 s 初始结构状态相匹配的 participant 入口，因此 `launch.sh` 会拒绝启动。

canonical source remains in the Windows project tree; this copy is an audit snapshot only.
