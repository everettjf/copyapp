# Compass 方位盘：点击到函数的证据链

设备是 iPhone XR（iOS 16.1.1），目标是系统 Compass `com.apple.compass`。本记录使用本地忽略的案例目录，文件未进入 Git。

1. `cases/experiment-original-bearing-chain-20261015/experiment.json`：iOS 界面点击 `(207,325)` 前后均为 Compass 前台；Frida 在 3.129 秒窗口内记录 `CompassView::tappedCompass:`、`setBearing` 和 `CompassBearingView::updateLayer` 各一次，`CompassPageViewController::updateDisplay:` 189 次。实验前后截图的哈希由候选生成器重新核对。窗口内调用并不自动等于点击因果关系，尤其是周期更新方法。
2. `cases/compass-bearing-candidates-20261015/`：`copyapp candidates` 检查精确设备与 Bundle ID，再把被调用的实例方法按类名和 selector 匹配到 XR 导出的 Compass Mach-O 的 Objective-C 元数据。二进制 SHA-256 为 `469bfd16314c225902ff56c5f33b9a20be1909b357a07a3b387b8c8878c155b1`；得到 `tappedCompass:` 静态地址 `0x100001960`。运行时 IMP 有 ASLR 与指针认证，未以地址相等证明函数身份。案例的源实验、截图、索引与结果均通过 `copyapp verify`。
3. `cases/compass-bearing-candidate-rea-20261015/`：以该二进制哈希和地址调用 REA/Ghidra 12.1.4，返回 `CompassView::tappedCompass:` 的函数体，Evidence ID `ev_5fe9c2f0ce67923a0c0c0163cddc3f8c05baaf7f2ccf83a5ca219b07899499bf`。伪代码显示读取 `_hasBearing`，有值时调用 `unsetBearing`，否则调用 `setBearing`。这是静态反编译结果；它与手机点击时两个相关方法各被调用一次的观察相符，但不还原作者源码。

4. `cases/compass-bearing-toggle-1-20261015/` 与 `cases/compass-bearing-toggle-2-20261015/`：连续两次 iCTRL 点击、Frida 计数和前后截图分别记录 `unsetBearing=1 / setBearing=0`（红色锁定标记消失）与 `unsetBearing=0 / setBearing=1`（标记恢复）。两次均记录 `tappedCompass:=1`，前后前台均为 Compass。这补上了静态分支的双方向真机行为，但没有采集参数和完整调用顺序。
5. `cases/compass-binding-probe-20261015/` 与 `cases/compass-binding-set-probe-20261015/`：Frida 对运行时 IMP 去除 arm64e 指针认证并定位到 Compass 模块。`tappedCompass:`、`setBearing`、`unsetBearing` 的模块偏移分别为 `0x1960`、`0x1978`、`0x1a08`，与同一 XR 导出 Mach-O 的静态方法地址减去 `0x100000000` 基址后的值一致；前两项实验各覆盖取消/设置一次。`copyapp candidates` 在 `cases/compass-pac-two-branches-20261015/` 复核了偏移和源证据哈希。偏移一致尚不能证明手机加载的代码字节与采集副本完全相同。

6. `cases/compass-hopper-tapped-20261015/`：对同一 XR 导出二进制（SHA-256 `469bfd16…`）及同一地址 `0x100001960` 调用 REA/Hopper。Evidence ID `ev_b55fc9669f12663205c28aec4e7413a411e0a2a4702b48532db8a8a716bc6e18`，伪代码同样读取 `_hasBearing` 并在两分支调用 `unsetBearing` / `setBearing`。这是独立反编译器对静态控制流的复核；Hopper 公共 Python API 未给出完整函数体范围，也不证明当前设备代码未经运行时修改。

7. `cases/compass-ghidra-set-bearing-20261015/`、`cases/compass-hopper-set-bearing-20261015/`、`cases/compass-ghidra-unset-bearing-20261015/` 和 `cases/compass-hopper-unset-bearing-20261015/`：两种 provider 分别分析 `0x100001978` 与 `0x100001a08`。共同确认 `_hasBearing` 置 1/清 0，随后向表盘、标签和背景发送 `setBearing` 消息。Ghidra 显示的数值实参与 Hopper 的寄存器级结果并不完全对应，因此数值解释保留待核对；Ghidra 对尾部调用的控制流也给出明确局限。真机双向点击观察与状态切换相符，但未跟踪所有子组件的参数。
8. `cases/compass-ghidra-update-layer-20261015/` 和 `cases/compass-hopper-update-layer-20261015/`：两种 provider 对 `CompassBearingView::updateLayer` 的 `0x100002014` 均给出角度计算、与 `_endAngle` 的差值比较，以及约大于 `0.001` 时写入并调用 `setNeedsLayout` 的路径。点击实验窗口内记录该方法一次调用。最终绘制细节和阈值单位尚未单独验证。

以上证据已收入 `cases/compass-xr-deep-report-v8-20261015/` 并通过 `copyapp verify`。下一步可继续追踪 `setBearing:` 的子组件实现和实际绘制。REA/Hopper 的启动机制及正常用户会话要求见 [REA 集成记录](rea-hopper-integration.md)。
