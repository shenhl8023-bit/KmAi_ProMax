# Windows 7 前置更新

本目录用于离线安装 KmAI 在 Windows 7 SP1 x64 上需要的系统前置更新。

## KB2533623

- 文件：`Windows6.1-KB2533623-x64.msu`
- 架构：x64
- SHA-256：`58b8b00113fa8b9657d8da5b14bae93f765f29651c81055e3d127d4a22e5c0d6`
- 安装方式：使用管理员权限运行 `install-kb2533623.bat`
- 安装后：必须手动重启 Windows 7，重启完成后再启动 KmAI

这个更新是操作系统前置条件，不能通过复制 KmAI 文件代替。安装脚本只在用户明确运行时调用 Windows Update Standalone Installer，不会由 `start_agent.bat`、`start_client_win7.bat` 或 3DMPS 生命周期自动调用，也不会自动重启计算机。

如果系统已经安装 KB2533623，脚本会提示已安装并直接退出。若系统安装了包含该修复的后续更新，也可以按现场补丁基线跳过本目录的安装；是否满足企业基线由管理员确认。
