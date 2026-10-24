const translations = {
  zh: {
    heroSource: "三种入口已合入 main；最新标签 v0.2.0 早于普通 iPhone 模式，请使用最新源码。",
    standardPlatformTitle: "非越狱 iOS",
    standardPlatformText: "通过签名的 XCTest 观察界面、辅助功能与 USB 截图，交付 UI 行为报告，再构建独立签名 App 并对照相同流程。无需原版 IPA、FairPlay 凭据、SSH 或 Frida。",
    standardPlatformScope: "已测越狱未激活的 iOS 26 样本及 iOS 17 普通模式回归；从未越狱设备未单独实测。",
    standardPlatformLink: "普通模式配置与任务",
    standardSetupGuide: "非越狱 iOS 配置",
    startStandard: "iOS · 普通",
    startStandardBackend: "无需越狱",
    startEnhancedBackend: "需要越狱",

    navTools: '逆向工具', navWorkflow: '工作流程', navArchitecture: '架构', navEvidence: '证据示例', navDevices: '支持平台', navStart: '开始使用',
    eyebrow: "iOS + macOS · 三种使用方案", heroOne: '看见内部。', heroTwo: '构建新可能。',
    heroSub: "非越狱 iOS、越狱 iOS 和 Mac App，三种方式分析已安装 App、独立实现选定行为。保留观察证据，交付可运行的 App 与对照结果。",
    heroStart: '快速上手', heroDocs: '阅读文档', heroDiscord: '到 Discord 交流', factPhases: "种使用方案", factTested: "个目标平台", factProgress: '默认原型评分',
    workflowTitle: '两个阶段，一条证据链。', workflowIntro: '从观察原版到审阅独立实现；每个阶段都留下可复查的案例。',
    phaseOneTag: '理解原版', phaseOneTitle: '理解真实行为', phaseOneText: "普通 iOS 观察界面与辅助功能；越狱 iOS 增加安装包、沙盒和运行时证据；macOS 采集 App 包、AX 与界面。审阅对应范围的报告与功能规格。",
    phaseOneA: "按路线采集 App 证据", phaseOneB: '界面流程与截图', phaseOneC: "普通 UI／增强运行时／Mac AX", phaseOneD: '审阅报告与功能规格',
    phaseTwoTag: '构建独立 APP', phaseTwoTitle: '按目标复刻', phaseTwoText: '构建独立的 iOS 或 macOS App。对照相同流程并逐图审阅，达到评分目标或耗尽轮数就停止。',
    phaseTwoA: '能力清单与目标', phaseTwoB: '独立源码、IPA 或 .app', phaseTwoC: '成对行为与视觉检查', phaseTwoD: '经验证交付与已知缺口',
    principle: '一张通过的截图只是一个数据点。可信的复刻来自连续的观察、判断和可重复检查。',
    architectureTitle: '把真实设备变成分析工具。', architectureIntro: '当前 Coding Agent 负责规划与实现，Copy APP 记录证据和检查；指定 iPhone 或 ChatComputer 虚拟 Mac 提供观察结果。',
    archAgent: '规划与解释', archMac: '调度、分析、构建', archOutputTitle: '可校验的产物', archOutput: '报告 · 源码 · IPA／.app · 对照',
    archTarget: "普通 iPhone／越狱 iPhone／虚拟 Mac",
    noteOneTitle: '看清实际发生的事。', noteOneText: '指定设备身份、安装包哈希、有界操作、截图和运行时跟踪都保存到本地证据案例。',
    noteTwoTitle: '每个结论都能找到依据。', noteTwoText: "普通 iOS 交付 UI 行为报告。越狱 iOS 可选 Ghidra／Hopper 原生分析；Mac 使用 App 包、AX 与界面证据。",
    noteThreeTitle: '只衡量选定的范围。', noteThreeText: '原版与独立 App 在同一准确环境中分别运行。交付明确列出通过行为、可见差异与未知范围。',
    toolsTitle: '选择你的逆向工具。',
    toolsIntro: '已直连两种反编译器，并组合动态跟踪和有界汇编。反编译按需启用，默认 provider 为 none。',
    toolDecompiler: '反编译器／按需启用', toolRuntime: '动态运行观察', toolAssembly: 'ARM64 反汇编',
    ghidraToolText: '指定函数伪代码，有界调用关系、基本块与指令引用。',
    ghidraToolSetup: '单独安装 Ghidra 与匹配 JDK；支持单函数、队列及选定间接调用调查。',
    hopperToolText: '通过本机 Python 脚本接口生成指定函数与候选队列的伪代码。',
    hopperToolSetup: '需要本机 Hopper 许可与已登录的 macOS 图形会话；运行时不依赖 REA。',
    fridaToolText: '在有界界面流程中跟踪指定 Objective-C 方法和选定原始入口。',
    fridaToolSetup: '需要匹配的宿主／手机服务；某个时间窗口内命中不单独证明 UI 因果。',
    llvmToolText: '使用 llvm-objdump 保存有界汇编，并跟随唯一局部直接调用／分支。',
    llvmToolSetup: '使用本机 Xcode 工具链；汇编与反编译伪代码分别记录。',
    toolIndexTitle: '内置安装包与 Objective-C 索引', toolIndexText: '无需反编译器即可检查 Mach-O 加载命令、类、selector 和方法地址。',
    toolRecoveryTitle: '加密安装包恢复', toolRecoveryText: "越狱设备可走受支持的恢复路线；Mac 离线恢复使用与 IPA 授权账号一致的本地 FairPlay 凭据。首次提取需受支持的越狱手机。",
    toolPlatformScope: "原生函数调查需要对应的代码和运行时证据，主要用于越狱 iOS。普通 iOS 侧重 UI；Mac 使用 App 包、AX 与界面证据。",
    toolIntegrationScope: 'REA 不是运行依赖；IDA Pro、Binary Ninja、radare2 暂无直接适配器。伪代码是生成证据，不是原作者源码。',
    toolsGuide: '安装条件、命令与 Agent 任务',
    platformsTitle: "iOS 两种方案，再加 Mac App。",
    platformsIntro: "按设备条件与需要的证据深度选择，三种方案都可继续独立实现和流程对照。",
    iosPlatformTitle: '越狱 iOS',
    iosPlatformText: "安装包与沙盒采集、界面重放、可选 Frida 跟踪和受支持的设备解密。增强证据与准确手机、系统及 App 构建绑定。",
    iosPlatformLink: '指定手机证据与限制',
    macPlatformTitle: 'macOS',
    macPlatformText: '通过 ChatComputer 使用电脑，采集准确 App／AX 证据，独立构建 .app，在专用虚拟 Mac 内对照流程并审阅快照恢复。',
    macPlatformScope: '自有编辑器 9/9 组选定对照通过，并有指定实体 Mac 复验；不代表任意 Mac 兼容或整 App 等价。',
    macPlatformLink: 'Mac 安装与 Agent 任务',
    heroVisualCaption: "非越狱 iOS · 越狱 iOS · Mac App",
    stocksImageLabel: '实际运行界面 / 独立离线示例',
    stocksTitle: '从源码，到运行中的 Mac App。',
    stocksText: '搜索股票、切换图表周期、管理本地自选列表。图中为独立 Stocks 示例在 macOS 上的实际运行界面，使用明确标注的离线演示数据。',
    stocksScope: '指定客体 9/9 组选定行为对照通过，原型评分 81/100；明显视觉差异仍保留。此图展示源码样例，不代表整 App 等价或实时行情服务。',
    stocksSource: '构建这个示例',
    macSetupGuide: 'macOS 安装步骤', footerReleases: '版本下载 ↗',
    visualTitle: '两个平台，都看得见。', visualIntro: '上方 Mac 示例展示独立 App 的实际运行效果。以下早期 iOS 图解展示观察、审阅与交付的证据链。',
    visualOneTitle: '01 / 系统架构', visualOneCaption: 'Mac 协调分析与构建，指定的 iPhone 提供观察数据。',
    visualTwoTitle: '02 / 证据', visualTwoCaption: '结论关联具体案例；Hopper 片段展示已保存证据，不是原始源码。',
    visualThreeTitle: '03 / 同机对照', visualThreeCaption: 'iPhone 14 上的一条 Calculator 流程已通过，但仍有视觉差异。',
    visualFourTitle: '04 / 交付', visualFourCaption: '经过审阅的报告和可运行 App，并标明实测覆盖与未解决的问题。',
    evidenceTitle: '看见证据，也看见边界。', evidenceIntro: '这些经过筛选的公开示例说明工作方式。完整案例、第三方二进制和沙盒内容仍留在本地。',
    pairTitle: '原版 ↔ 独立复刻版', pairCaption: 'iPhone 14 / iOS 17：选定的 7 + 8 = 15 流程通过，但仍有视觉差异。',
    ios26Title: '一次 iOS 26 观察', ios26Caption: 'iPhone 11 上的原版 Calculator。仅凭这张图不能证明复刻版等价。',
    hopperTitle: '原生代码的一条线索', hopperCaption: '基于已保存的 Hopper 输出绘制，并非工具窗口截图或原作者源码。',
    sandboxTitle: '有界的沙盒目录', sandboxCaption: '仅包含路径元数据；本案例没有复制文件内容，也没有证明数据模型。',
    articleLink: '阅读完整图文介绍',
    devicesTitle: '在真实手机上验证。', devicesIntro: '支持声明以设备证据为准，限定在已记录流程内，不代表任意 App 或全部功能。',
    verified: '流程已验证', inProgress: '验证进行中', device16: '已验证分析、包恢复、界面和选定复刻流程。',
    device17: '已验证分析、签名安装以及原版与复刻版对照。', device26: 'Calculator 与 Clock 的选定复刻流程已通过；仍有轻微视觉差异。',
    validationLabel: '尚待验证', validationTitle: '这些测试尚未证明什么',
    validationOne: 'iOS 17 指定回归之外，iOS 16／26 上改动后的 iCTRL 清理逻辑',
    validationTwo: 'XR 可选开发者文件列表，以及重启／重新越狱后的持续可用性',
    validationThree: '第二台实体 Mac 的首次手机配置',
    validationFour: '任意 App 的覆盖、整 App 功能等价和像素级一致',
    validationLink: '当前状态与验收门槛',
    deviceEvidence: '阅读真机证据与限制', startTitle: '从你的 App 开始。',
    startText: "选择一种方案、替换 App 名称，把任务复制给 Codex 或 Claude Code。Agent 先安装 CLI、检查环境，再处理目标 App。",
    startStepOne: '打开本地 Coding Agent', startStepOneText: '在 Mac 上使用能执行本地命令的 Codex 或 Claude Code。',
    startStepTwo: "选择一种使用方案", startStepTwoText: "普通 iOS、越狱增强 iOS 或 Mac，分别提供任务和安装检查。",
    startStepThree: '完成必要授权', startStepThreeText: '按具体提示完成设备信任或客体授权，Agent 再继续目标 App 的工作。',
    startNoExtension: '无需专属扩展；Agent 直接读取源码仓库里的 Skill。',
    startMacBackend: 'ChatComputer', startIOS: "iOS · 增强", startPrepare: '你需要准备', startAgentDoes: 'Agent 安装与检查',
    startTaskLabel: '复制给 CODEX / CLAUDE CODE',
    startDefaults: '输出保存在唯一 output/ 任务目录，分开 project/ 与 evidence/。默认审阅评分 80 分，最多三轮实现／检查；明确选定范围和剩余差异。',
    setupGuide: 'iOS 安装步骤', contribute: '参与贡献', copy: '复制任务',
    footerLine: '可以复查的证据。可以实测的软件。', footerDiscord: 'Discord ↗', footerDocs: '文档 ↗', footerContribute: '贡献指南 ↗'
  }
};

const quickstarts = {
  "en": {
    "macos": {
      "requirements": "Apple Silicon · macOS 27 · 16 GB+ RAM · about 70 GB free. Complete virtual Mac initialization and its requested permissions; install your target App inside that guest.",
      "source": "ChatComputer requirements · checked 2026-10-22 ↗",
      "sourceUrl": "https://github.com/chatcomputer/chatcomputer#install",
      "agent": "Python 3.9+, repository CLI, Swift/macOS SDK, ChatComputer and the guest collector. It verifies the exact guest and target App before analysis.",
      "checkOnly": "Only checking setup? Append: “Stop after verified environment registration and one target-App screenshot/AX observation; do not analyze or rebuild yet.”",
      "prompt": "Use https://github.com/everettjf/copyapp and ChatComputer to analyze and independently rebuild selected behavior of the macOS App “APP NAME”.\nClone into a new directory if needed, or reuse my existing checkout. Read AGENTS.md, skills/copyapp-mac/SKILL.md and docs/macos-support.md first.\nCheck the host against ChatComputer's current requirements, Python 3.9+ and the Swift/macOS SDK. If needed, prepare the repository CLI with sh scripts/bootstrap-macos.sh and install ChatComputer from its official distribution.\nGuide me through guest initialization and required system permissions. Use .venv/bin/copyapp mac doctor, deploy the bounded collector and register the exact guest. Confirm the target App is installed inside that virtual Mac; identify its exact build before analysis.\nUse the current agent session for flow discovery, report review and implementation. Install the independent App separately, compare the same flows and review every screenshot. Preserve iOS support; do not start another agent or ChatComputer's model loop.\nUse a unique output/ job with project/ and evidence/. Follow docs/fidelity.md: default grade 80/100, at most three implementation/check cycles including the first. Stop at the target or cycle limit and deliver source, runnable artifacts, verified scope and remaining differences."
    },
    "ios": {
      "requirements": "A Mac and an unlocked jailbroken iPhone connected over USB, with your target App installed. Approve device trust; SSH fingerprint checks, permissions and signing access may follow.",
      "source": "iOS setup requirements ↗",
      "sourceUrl": "https://github.com/everettjf/copyapp/blob/main/docs/setup.md",
      "agent": "Python 3.9+, repository CLI and exact phone/App identity. Then it configures the required SSH, UI/runtime tools and build/signing route for this device.",
      "checkOnly": "Only checking setup? Append: “Stop after a verified USB survey, identify the phone and App, and list remaining prerequisites; do not analyze or rebuild yet.”",
      "prompt": "Use https://github.com/everettjf/copyapp to analyze and independently rebuild selected behavior of “APP NAME” on my USB-connected jailbroken iPhone.\nClone into a new directory if needed, or reuse my existing checkout. Read AGENTS.md and skills/copyapp-start/SKILL.md first.\nCheck Python 3.9+ and run sh scripts/bootstrap-macos.sh if the repository CLI is missing. Identify the exact phone and App; complete the initial USB check, then configure only the analysis/rebuild prerequisites this device needs. Use --mode enhanced for UI-first collection with enhancement, and the explicit investigation/report commands for deeper function reasoning.\nWork in the current agent session through a reviewed report, independent implementation, installation and same-device comparison. Ask me for the specific device-side trust, permission or signing action when needed.\nUse a unique output/ job with project/ and evidence/. Follow docs/fidelity.md: default grade 80/100, at most three implementation/check cycles including the first. Stop at the target or cycle limit and deliver source, runnable artifacts, verified scope and remaining differences."
    },
    "standard": {
      "requirements": "A Mac with Xcode, an unlocked USB iPhone with the target App installed, Developer Mode, device trust and development signing.",
      "source": "Standard iPhone setup and evidence ↗",
      "sourceUrl": "https://github.com/everettjf/copyapp/blob/main/docs/ios-standard-mode.md",
      "agent": "Python 3.9+, CLI, exact USB phone/App identity, a development-signed iCTRL XCTest runner and USB installation. Collection needs no original IPA, FairPlay credential, SSH or Frida.",
      "checkOnly": "Only checking setup? Append: “Stop after a verified standard-mode capability check; list signing or runner setup still needed.”",
      "prompt": "Use https://github.com/everettjf/copyapp to observe and independently rebuild selected behavior of “APP NAME” on my USB-connected non-jailbroken iPhone.\nUse the latest main checkout. Read AGENTS.md, skills/copyapp-start/SKILL.md and docs/ios-standard-mode.md first. Prepare the CLI with sh scripts/bootstrap-macos.sh if needed.\nIdentify the exact USB phone and App. Use --mode standard; check Xcode, Developer Mode, device trust and development signing. Prepare the signed iCTRL XCTest runner and install over USB.\nDiscover representative UI flows, review screenshots and accessibility evidence, and deliver a reviewed UI behavior report. Standard collection needs no IPA or FairPlay credential. Implement an independent App with its own Bundle ID, sign and install it over USB, then compare the same flows and review every screenshot pair in the current agent session.\nUse a unique output/ job with project/ and evidence/. Follow docs/fidelity.md: default grade 80/100, at most three implementation/check cycles including the first. Deliver source, runnable artifacts, verified scope and remaining differences. Keep native function and private sandbox claims outside the UI-only report."
    }
  },
  "zh": {
    "macos": {
      "requirements": "Apple Silicon · macOS 27 · 至少 16GB 内存 · 约 70GB 可用空间。完成虚拟 Mac 初始化和必要授权，目标 App 要安装在客体内。",
      "source": "ChatComputer 官方要求 · 2026-10-22 核对 ↗",
      "sourceUrl": "https://github.com/chatcomputer/chatcomputer#install",
      "agent": "Python 3.9+、仓库 CLI、Swift／macOS SDK、ChatComputer 和客体采集器。分析前确认准确虚拟 Mac 与目标 App 身份。",
      "checkOnly": "只检查安装？在任务末尾加：“完成经校验的环境登记和一次目标 App 截图／AX 观察后停止，先不分析或复刻。”",
      "prompt": "请使用 https://github.com/everettjf/copyapp 和 ChatComputer，分析并独立复刻 macOS 上「App 名称」的选定行为。\n需要时克隆到新目录，或复用已有检出。先阅读 AGENTS.md、skills/copyapp-mac/SKILL.md 和 docs/macos-support.zh-CN.md。\n检查宿主是否满足 ChatComputer 当前要求，以及 Python 3.9+、Swift／macOS SDK。需要时运行 sh scripts/bootstrap-macos.sh 安装仓库 CLI，并从官方渠道安装 ChatComputer。\n引导我完成虚拟 Mac 初始化及必要系统授权。执行 .venv/bin/copyapp mac doctor，部署有界采集器并登记准确客体；确认目标 App 已安装在虚拟 Mac 中，识别准确构建后再分析。\n在当前 Agent 会话完成流程发现、报告审阅和实现。新 App 分开安装，对照相同流程并逐张审阅截图。保留 iOS 支持，不启动另一个 Agent 或 ChatComputer 内置模型循环。\n在 output/ 下建立唯一任务目录，分开 project/ 和 evidence/。按 docs/fidelity.md 执行：默认 80 分，最多三轮实现／检查，首轮计入；达标或轮数耗尽就停止，交付源码、可运行产物、已验证范围与剩余差异。"
    },
    "ios": {
      "requirements": "Mac、USB 连接并解锁的越狱 iPhone，目标 App 已装在手机上。确认设备信任；后续可能还需核对 SSH 指纹、系统授权和签名条件。",
      "source": "iOS 安装条件与步骤 ↗",
      "sourceUrl": "https://github.com/everettjf/copyapp/blob/main/docs/setup.zh-CN.md",
      "agent": "Python 3.9+、仓库 CLI 和准确手机／App 身份，再按这台设备配置 SSH、界面／运行时工具与构建签名路线。",
      "checkOnly": "只检查安装？在任务末尾加：“完成经校验的 USB survey，告诉我准确手机、App 和剩余依赖后停止，先不分析或复刻。”",
      "prompt": "请使用 https://github.com/everettjf/copyapp，分析并独立复刻 USB 连接的越狱 iPhone 上「App 名称」的选定行为。\n需要时克隆到新目录，或复用已有检出。先阅读 AGENTS.md 和 skills/copyapp-start/SKILL.md。\n检查 Python 3.9+；仓库 CLI 未安装时执行 sh scripts/bootstrap-macos.sh。识别准确的手机和 App，先完成 USB 首次检查，再按这台设备配置分析／复刻需要的依赖。增强 UI 采集使用 --mode enhanced，深入函数推理继续使用显式调查与报告命令。\n在当前 Agent 会话完成报告审阅、独立实现、安装与同机对照。需要手机信任、系统授权或签名条件时，告诉我具体操作。\n在 output/ 下建立唯一任务目录，分开 project/ 和 evidence/。按 docs/fidelity.md 执行：默认 80 分，最多三轮实现／检查，首轮计入；达标或轮数耗尽就停止，交付源码、可运行产物、已验证范围与剩余差异。"
    },
    "standard": {
      "requirements": "装有 Xcode 的 Mac、USB 连接并解锁的 iPhone、已安装的目标 App、开发者模式、设备信任和开发签名。",
      "source": "普通 iPhone 配置与实测范围 ↗",
      "sourceUrl": "https://github.com/everettjf/copyapp/blob/main/docs/ios-standard-mode.zh-CN.md",
      "agent": "Python 3.9+、CLI、准确 USB 手机／App 身份、开发签名的 iCTRL XCTest runner 和 USB 安装。采集无需原版 IPA、FairPlay 凭据、SSH 或 Frida。",
      "checkOnly": "只检查安装？加：“完成经校验的普通模式能力检查，列出还缺的签名或 runner 配置后停止。”",
      "prompt": "请使用 https://github.com/everettjf/copyapp，观察并独立复刻 USB 连接的非越狱 iPhone 上「App 名称」的选定行为。\n使用最新 main 检出。先阅读 AGENTS.md、skills/copyapp-start/SKILL.md 和 docs/ios-standard-mode.zh-CN.md；需要时执行 sh scripts/bootstrap-macos.sh 安装 CLI。\n识别准确的 USB 手机和 App，使用 --mode standard，检查 Xcode、开发者模式、设备信任和开发签名，准备签名的 iCTRL XCTest runner 并通过 USB 安装。\n发现代表性界面流程，审阅截图和辅助功能证据，交付审阅后的 UI 行为报告；普通采集无需 IPA 或 FairPlay 凭据。以独立 Bundle ID 实现 App，开发签名后通过 USB 安装，在当前 Agent 会话对照同机流程并逐张审阅截图。\n在 output/ 下建立唯一任务目录，分开 project/ 和 evidence/。按 docs/fidelity.md 执行：默认 80 分，最多三轮实现／检查，首轮计入；交付源码、可运行产物、已验证范围与剩余差异。UI 报告不作原生函数或私有沙盒结论。"
    }
  }
};

const languageButton = document.querySelector('#language');
const copyButton = document.querySelector('#copyCommand');
let activePlatform = 'standard';
let copyResetTimer;

function renderQuickstart() {
  const zh = document.documentElement.lang === 'zh-CN';
  const task = quickstarts[zh ? 'zh' : 'en'][activePlatform];
  document.querySelector('#setupRequirements').textContent = task.requirements;
  document.querySelector('#setupAgent').textContent = task.agent;
  document.querySelector('#setupCheckOnly').textContent = task.checkOnly;
  document.querySelector('#agentPrompt').textContent = task.prompt;
  const source = document.querySelector('#requirementsSource');
  source.textContent = task.source;
  source.href = task.sourceUrl;
  document.querySelectorAll('[data-platform]').forEach(button => {
    button.setAttribute('aria-pressed', String(button.dataset.platform === activePlatform));
  });
  document.querySelector('.platform-picker').setAttribute('aria-label', zh ? '目标平台' : 'Target platform');
  document.querySelector('.terminal pre').setAttribute('aria-label', zh ? 'Agent 任务' : 'Agent task');
  const label = {standard: zh ? '非越狱 iOS' : 'non-jailbroken iOS', ios: zh ? '越狱 iOS' : 'jailbroken iOS', macos: 'macOS'}[activePlatform];
  copyButton.setAttribute('aria-label', zh ? '复制' + label + '任务' : 'Copy ' + label + ' agent task');
  copyButton.textContent = zh ? '复制任务' : 'COPY TASK';
  document.querySelector('#copyStatus').textContent = '';
  clearTimeout(copyResetTimer);
}

function setLanguage(language) {
  const zh = language === 'zh';
  document.documentElement.lang = zh ? 'zh-CN' : 'en';
  document.title = zh ? 'Copy APP — 观察、理解、复刻' : 'Copy APP — Observe. Understand. Rebuild.';
  document.querySelectorAll('[data-i18n]').forEach((element) => {
    const key = element.dataset.i18n;
    if (zh && translations.zh[key]) element.textContent = translations.zh[key];
    else if (element.dataset.english) element.textContent = element.dataset.english;
  });
  const statusUrl = 'https://github.com/everettjf/copyapp/blob/main/docs/current-status' + (zh ? '.zh-CN' : '') + '.md';
  for (const id of ['statusLink', 'deviceStatusLink']) document.getElementById(id).href = statusUrl;
  document.getElementById('toolsGuideLink').href = 'https://github.com/everettjf/copyapp/blob/main/docs/reverse-engineering-tools' + (zh ? '.zh-CN' : '') + '.md';
  document.getElementById('macGuideLink').href = 'https://github.com/everettjf/copyapp/blob/main/docs/macos-support' + (zh ? '.zh-CN' : '') + '.md';
  document.getElementById('macSetupLink').href = 'https://github.com/everettjf/copyapp/blob/main/docs/macos-support' + (zh ? '.zh-CN.md#安装与首次使用' : '.md#install-and-first-use');
  document.getElementById('iosSetupLink').href = 'https://github.com/everettjf/copyapp/blob/main/docs/setup' + (zh ? '.zh-CN' : '') + '.md';
  for (const id of ['standardGuideLink', 'standardSetupLink']) document.getElementById(id).href = 'https://github.com/everettjf/copyapp/blob/main/docs/ios-standard-mode' + (zh ? '.zh-CN' : '') + '.md';
  languageButton.setAttribute('aria-label', zh ? 'Switch to English' : '切换到中文');
  renderQuickstart();
  try { localStorage.setItem('copyapp-language', language); } catch (_) { /* private mode */ }
}

document.querySelectorAll('[data-i18n]').forEach((element) => { element.dataset.english = element.textContent; });
let initialLanguage = 'en';
try { initialLanguage = localStorage.getItem('copyapp-language') === 'zh' ? 'zh' : 'en'; } catch (_) { /* private mode */ }
setLanguage(initialLanguage);
languageButton.addEventListener('click', () => setLanguage(document.documentElement.lang === 'en' ? 'zh' : 'en'));
document.querySelectorAll('[data-platform]').forEach(button => {
  button.addEventListener('click', () => {
    activePlatform = button.dataset.platform;
    renderQuickstart();
  });
});
copyButton.addEventListener('click', async () => {
  const prompt = document.querySelector('#agentPrompt');
  const text = prompt.textContent.trim();
  try {
    await navigator.clipboard.writeText(text);
    if (prompt.textContent.trim() !== text) return;
    const zh = document.documentElement.lang === 'zh-CN';
    copyButton.textContent = zh ? '已复制' : 'COPIED';
    document.querySelector('#copyStatus').textContent = zh ? '已复制。粘贴到本地 Agent，并替换 App 名称。' : 'Copied. Paste into your local agent and replace APP NAME.';
    copyResetTimer = setTimeout(() => {
      copyButton.textContent = document.documentElement.lang === 'zh-CN' ? '复制任务' : 'COPY TASK';
    }, 1800);
  } catch (_) {
    if (prompt.textContent.trim() !== text) return;
    const range = document.createRange();
    range.selectNodeContents(prompt);
    const selection = window.getSelection();
    selection.removeAllRanges();
    selection.addRange(range);
    document.querySelector('#copyStatus').textContent = document.documentElement.lang === 'zh-CN' ? '任务已选中，请手动复制。' : 'Task selected. Copy it manually.';
  }
});
