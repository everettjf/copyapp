const translations = {
  zh: {
    navWorkflow: '工作流程', navArchitecture: '架构', navEvidence: '证据示例', navDevices: '支持平台', navStart: '开始使用',
    eyebrow: 'v0.2.0 · 越狱 iOS + macOS', heroOne: '看见内部。', heroTwo: '构建新可能。',
    heroSub: '分析越狱 iPhone 上的 App，或通过 ChatComputer 分析 macOS App。独立实现选定行为，交付可运行 App，每一项结论都有证据来源。',
    heroStart: '开始探索', heroDocs: '阅读文档', heroDiscord: '到 Discord 交流', factPhases: '个支持平台', factTested: '台指定 iPhone 已测', factProgress: '默认原型评分',
    workflowTitle: '两个阶段，一条证据链。', workflowIntro: '从观察原版到审阅独立实现；每个阶段都留下可复查的案例。',
    phaseOneTag: '理解原版', phaseOneTitle: '理解真实行为', phaseOneText: 'iOS 采集安装包、沙盒和运行时证据；macOS 采集 App 包、AX 和界面证据。审阅有来源的报告与功能规格。',
    phaseOneA: '已安装包与沙盒', phaseOneB: '界面流程与截图', phaseOneC: 'iOS 运行时／macOS 辅助功能', phaseOneD: '审阅报告与功能规格',
    phaseTwoTag: '构建独立 APP', phaseTwoTitle: '按目标复刻', phaseTwoText: '构建独立的 iOS 或 macOS App。对照相同流程并逐图审阅，达到评分目标或耗尽轮数就停止。',
    phaseTwoA: '能力清单与目标', phaseTwoB: '独立源码、IPA 或 .app', phaseTwoC: '成对行为与视觉检查', phaseTwoD: '经验证交付与已知缺口',
    principle: '一张通过的截图只是一个数据点。可信的复刻来自连续的观察、判断和可重复检查。',
    architectureTitle: '把真实设备变成分析工具。', architectureIntro: '当前 Coding Agent 负责规划与实现，Copy APP 记录证据和检查；指定 iPhone 或 ChatComputer 虚拟 Mac 提供观察结果。',
    archAgent: '规划与解释', archMac: '调度、分析、构建', archOutputTitle: '可校验的产物', archOutput: '报告 · 源码 · IPA／.app · 对照',
    archTarget: '越狱 iPhone／虚拟 Mac',
    noteOneTitle: '看清实际发生的事。', noteOneText: '指定设备身份、安装包哈希、有界操作、截图和运行时跟踪都保存到本地证据案例。',
    noteTwoTitle: '每个结论都能找到依据。', noteTwoText: '可选的 iOS 原生分析使用 Ghidra 或 Hopper；macOS 界面证据证明选定行为，不代表深层函数语义。',
    noteThreeTitle: '只衡量选定的范围。', noteThreeText: '原版与独立 App 在同一准确环境中分别运行。交付明确列出通过行为、可见差异与未知范围。',
    platformsTitle: '越狱 iOS，也支持 macOS。',
    platformsIntro: '共用证据工作流，平台工具各自独立。v0.2.0 中的 macOS 仍为实验性支持。',
    iosPlatformTitle: '越狱 iOS',
    iosPlatformText: '保留已有 iOS 16／17／26 工作流：已安装 App、沙盒取证、有界界面重放和独立签名复刻。',
    iosPlatformLink: '指定手机证据与限制',
    macPlatformTitle: 'macOS · 实验性支持',
    macPlatformText: '通过 ChatComputer 使用电脑，采集准确 App／AX 证据，独立构建 .app，在专用虚拟 Mac 内对照流程并审阅快照恢复。',
    macPlatformScope: '自有编辑器 9/9 组选定对照通过，并有指定实体 Mac 复验；不代表任意 Mac 兼容或整 App 等价。',
    macPlatformLink: 'Mac 安装与 Agent 任务',
    heroVisualCaption: '越狱 iOS + macOS，共用证据工作流，交付独立 App。',
    stocksImageLabel: '实际运行界面 / 独立离线示例',
    stocksTitle: '从源码，到运行中的 Mac App。',
    stocksText: '搜索股票、切换图表周期、管理本地自选列表。图中为独立 Stocks 示例在 macOS 上的实际运行界面，使用明确标注的离线演示数据。',
    stocksScope: '指定客体 9/9 组选定行为对照通过，原型评分 81/100；明显视觉差异仍保留。此图展示源码样例，不代表整 App 等价或实时行情服务。',
    stocksSource: '构建这个示例',
    macSetupGuide: 'macOS 安装指南', footerReleases: '版本下载 ↗',
    agentPrompt: '请用 https://github.com/everettjf/copyapp 分析越狱 iOS 或 macOS 上的「App 名称」，并独立实现选定行为。\n先读 AGENTS.md；iOS 加载 skills/copyapp-start/SKILL.md，macOS 与 ChatComputer 加载 skills/copyapp-mac/SKILL.md。在当前 Agent 会话执行。\n默认使用 output/，分开 project/ 与 evidence/；目标 80 分，最多三轮。对照选定流程、逐图审阅，并交付可运行产物与剩余差异。',
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
    deviceEvidence: '阅读真机证据与限制', startTitle: '把一个任务交给你的 Agent。',
    startText: '在 Mac 上复制给 Codex 或 Claude Code，替换 App 名称并选择越狱 iOS 或 macOS，Agent 会加载对应仓库 Skill。',
    setupGuide: 'iOS 安装指南', contribute: '参与贡献', copy: '复制', terminalReady: '已检查设备身份及截图能力',
    footerLine: '可以复查的证据。可以实测的软件。', footerDiscord: 'Discord ↗', footerDocs: '文档 ↗', footerContribute: '贡献指南 ↗'
  }
};

const languageButton = document.querySelector('#language');
const copyButton = document.querySelector('#copyCommand');

function setLanguage(language) {
  const zh = language === 'zh';
  document.documentElement.lang = zh ? 'zh-CN' : 'en';
  document.title = zh ? 'Copy APP — 观察、理解、复刻' : 'Copy APP — Observe. Understand. Rebuild.';
  document.querySelectorAll('[data-i18n]').forEach((element) => {
    const key = element.dataset.i18n;
    if (zh && translations.zh[key]) element.textContent = translations.zh[key];
    else if (element.dataset.english) element.textContent = element.dataset.english;
  });
  const statusUrl = zh
    ? 'https://github.com/everettjf/copyapp/blob/main/docs/current-status.zh-CN.md'
    : 'https://github.com/everettjf/copyapp/blob/main/docs/current-status.md';
  for (const id of ['statusLink', 'deviceStatusLink']) {
    const link = document.getElementById(id);
    if (link) link.href = statusUrl;
  }
  for (const id of ['macGuideLink', 'macSetupLink']) {
    document.getElementById(id).href = 'https://github.com/everettjf/copyapp/blob/main/docs/macos-support' + (zh ? '.zh-CN' : '') + '.md';
  }
  copyButton.setAttribute('aria-label', zh ? '复制 Agent 任务' : 'Copy agent task');
  languageButton.setAttribute('aria-label', zh ? 'Switch to English' : '切换到中文');
  try { localStorage.setItem('copyapp-language', language); } catch (_) { /* private mode */ }
}

document.querySelectorAll('[data-i18n]').forEach((element) => { element.dataset.english = element.textContent; });
let initialLanguage = 'en';
try { initialLanguage = localStorage.getItem('copyapp-language') === 'zh' ? 'zh' : 'en'; } catch (_) { /* private mode */ }
setLanguage(initialLanguage);
languageButton.addEventListener('click', () => setLanguage(document.documentElement.lang === 'en' ? 'zh' : 'en'));
copyButton.addEventListener('click', async () => {
  try {
    await navigator.clipboard.writeText(document.querySelector('#agentPrompt').textContent.trim());
    const original = copyButton.textContent;
    copyButton.textContent = document.documentElement.lang === 'en' ? 'COPIED' : '已复制';
    setTimeout(() => { copyButton.textContent = original; }, 1800);
  } catch (_) {
    copyButton.textContent = document.documentElement.lang === 'en' ? 'SELECT TASK' : '请选中任务';
  }
});
