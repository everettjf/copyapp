const translations = {
  zh: {
    navWorkflow: '工作流程', navArchitecture: '架构', navEvidence: '证据示例', navDevices: '实测设备', navStart: '开始使用',
    eyebrow: '开源项目 · 真机证据', heroOne: '看见内部。', heroTwo: '构建新可能。',
    heroSub: '在越狱 iPhone 上分析真实 iOS App；把选定行为实现成独立 App。每一项结论都能追溯到证据。',
    heroStart: '开始探索', heroDocs: '阅读文档', factPhases: '相连的阶段', factTested: '台真机已测', factProgress: 'iOS 世代',
    workflowTitle: '两个阶段，一条证据链。', workflowIntro: '从观察原版到审阅独立实现；每个阶段都留下可复查的案例。',
    phaseOneTag: '理解原版', phaseOneTitle: '深度分析', phaseOneText: '采集 App 包、沙盒、界面和运行时证据。检查 Mach-O 与选定方法，写出有来源的报告与功能规格。',
    phaseOneA: '已安装包与沙盒', phaseOneB: '界面流程与截图', phaseOneC: 'Frida 跟踪与原生代码', phaseOneD: '审阅报告与功能规格',
    phaseTwoTag: '构建独立 APP', phaseTwoTitle: '按目标复刻', phaseTwoText: '制定现实的覆盖目标，构建并安装独立 iOS App，在真机上重放同样流程并审阅差异。',
    phaseTwoA: '能力清单与目标', phaseTwoB: '新 Xcode 工程与签名 IPA', phaseTwoC: '成对行为与视觉检查', phaseTwoD: '经验证交付与已知缺口',
    principle: '一张通过的截图只是一个数据点。可信的复刻来自连续的观察、判断和可重复检查。',
    architectureTitle: '把真实设备变成分析工具。', architectureIntro: 'Coding Agent 驱动工作流；Mac 协调采集与构建，手机提供事实依据。',
    archAgent: '规划与解释', archMac: '调度、分析、构建', archOutputTitle: '可校验的产物', archOutput: '报告 · 源码 · IPA · 对照结果',
    noteOneTitle: '看清实际发生的事。', noteOneText: '指定设备身份、安装包哈希、有界操作、截图和运行时跟踪都保存到本地证据案例。',
    noteTwoTitle: '每个结论都能找到依据。', noteTwoText: '原生分析可使用项目工具、Ghidra 或 Hopper。伪代码是待审阅证据，不是原始源码。',
    noteThreeTitle: '只衡量选定的范围。', noteThreeText: '原版与复刻版分别在同一台手机上运行。最终交付列出通过项、视觉差异与未知项。',
    visualTitle: '四张图看懂工作流。', visualIntro: '从手机证据到可衡量的独立复刻。点击图片可查看原图。',
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
    validationOne: 'iOS 17 复刻版上 iCTRL 多步重放的稳定性',
    validationTwo: 'XR 可选开发者文件列表，以及重启／重新越狱后的持续可用性',
    validationThree: '第二台实体 Mac 的首次手机配置',
    validationFour: '任意 App 的覆盖、整 App 功能等价和像素级一致',
    validationLink: '当前状态与验收门槛',
    deviceEvidence: '阅读真机证据与限制', startTitle: '第一份观察，从一条命令开始。',
    startText: '连接、解锁并信任 iPhone。在 Mac 安装 CLI，运行引导式 USB 检查。需要深度分析时再增加越狱服务。',
    setupGuide: '完整安装指南', contribute: '参与贡献', copy: '复制', terminalReady: '已检查设备身份及截图能力',
    footerLine: '可以复查的证据。可以实测的软件。', footerDocs: '文档 ↗', footerContribute: '贡献指南 ↗'
  }
};

const languageButton = document.querySelector('#language');
const copyButton = document.querySelector('#copyCommand');
const commands = 'git clone https://github.com/everettjf/copyapp.git\ncd copyapp\nsh scripts/bootstrap-macos.sh\n.venv/bin/copyapp onboard';

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
    await navigator.clipboard.writeText(commands);
    const original = copyButton.textContent;
    copyButton.textContent = document.documentElement.lang === 'en' ? 'COPIED' : '已复制';
    setTimeout(() => { copyButton.textContent = original; }, 1800);
  } catch (_) {
    copyButton.textContent = document.documentElement.lang === 'en' ? 'SELECT COMMANDS' : '请选中命令';
  }
});
