# Prepare a FairPlay credential for offline iOS IPA analysis

[中文说明](#中文说明) · [standard/enhanced modes](ios-standard-mode.md) · [acceptance ledger](ios-device-support-acceptance.md)

`credential-retrieve` prepares a reusable account credential from one explicitly selected jailbroken iPhone and an installed App Store App. The later `decrypt-offline` command runs on the Mac using local files. Standard-mode UI collection does not need this preparation or a credential.

The phone's App and the IPA must belong to the same account. An ipatool login alone does not supply this credential. A successful run validates the recovered value against the installed App's SINF; passing `--package-case` also checks the selected IPA's account and SINF before publishing the credential.

## First preparation

Use Xcode's iPhoneOS SDK, `make`, `ldid`, the optional Python cryptography dependency, and the pinned upstream sources:

```sh
sh scripts/bootstrap-ios-host-tools.sh --offline
.venv/bin/python -m pip install '.[offline]'
```

The phone must already be paired and jailbroken, with a verified SSH key and pinned host key. Follow [setup](setup.md) / `copyapp onboard` for a new device. This command never changes SSH authentication or installs a jailbreak. Specify the exact device and installed App; it does not select the first connected phone or first App.

```sh
.venv/bin/copyapp credential-retrieve \
  --udid <JAILBROKEN_DEVICE_UDID> --bundle <INSTALLED_APP_BUNDLE> \
  --credential-ref <NEW_LOCAL_ALIAS> \
  --package-case cases/store-package \
  --out cases/credential-preparation
.venv/bin/copyapp verify cases/credential-preparation
```

`--package-case` is optional and must be a verified package for the same Bundle ID. If the IPA contains multiple license selectors, use `--sinf-member <EXACT_ZIP_MEMBER>` to select one. The installed App and package may have different versions; successful license validation establishes the credential's applicability, not matching installed code. Use separate package/device code checks for that claim.

Per-device SSH profiles are reused. Explicit `--ssh-port`, `--ssh-identity` and `--ssh-known-hosts` override them. The default SSH user is `mobile`; the named RootHide iPhone 14 / iOS 17.3.1 passed through that route. `--ssh-user root` is available for an existing verified root-key route, without automatic authentication fallback. This does not establish support for every jailbreak, phone or iOS version.

The command checks 33 public upstream source hashes at revision `1bad106ee1698c6d9c483f67d898183ffa4c6eb3`, copies only those inputs and rebuilds/signs the native helpers. It verifies USB, authenticated SSH and native FairPlay device identities, observes a bounded FairPlay daemon restart using a temporary App copy, validates SINF decoding, and removes remote temporary files before saving. The original App is not replaced. Build products already present in the upstream checkout are not trusted or reused.

Credentials use opaque aliases, remain in the ignored private store, and are created with mode 0600 under a 0700 directory. Existing aliases are never overwritten. The evidence case contains stage results, public tool provenance and optional package evidence; it excludes credential bytes, their hash, the actual storage path and raw account/session output. Verification checks saved provenance and record consistency without reading the credential or certifying the truth of every runtime observation. Failed cases are retained with a fixed error code.

## Later use on the Mac

```sh
.venv/bin/copyapp decrypt-offline --package cases/store-package \
  --credential-ref <LOCAL_ALIAS> --out cases/offline-package
.venv/bin/copyapp verify cases/offline-package
.venv/bin/copyapp offline-cross-check --offline cases/offline-package \
  --device <VERIFIED_MATCHING_DEVICE_RECOVERY> --out cases/offline-cross-check
.venv/bin/copyapp verify cases/offline-cross-check
```

Offline recovery audits every program and resource. Structural success alone is not proof of correct plaintext. `offline-cross-check` compares all recovered programs—including extensions—with independently verified device recovery of matching encrypted code, UUIDs and encryption spans. An analysis IPA has changed signatures and is not claimed installable.

For an installed wheel invoked outside the checkout, set `COPYAPP_SOURCE_ROOT` to the checkout containing the ignored toolchains, SSH profiles and credential store. Explicit tool, store and SSH paths remain available. A custom credential store must be outside the evidence case; protect and exclude it from version control separately.

## 中文说明

首次获取用 `credential-retrieve`，后续在 Mac 上用 `decrypt-offline`。普通模式的 UI 采集不需要做这一步。

手机上选定的 App 和待分析 IPA 必须属于同一个账号。`--package-case` 可提前核对账号并验证该 IPA 的授权；只有登录 ipatool 不等于已经有凭据。出现多个授权选择时，用 `--sinf-member` 指定准确的 ZIP 成员。

默认沿用准确手机已验证的 mobile SSH 路由，本次 iPhone 14 / iOS 17.3.1 RootHide 已通过；不能把这一结果推广到任意越狱环境。需要 root 的既有环境可显式传 `--ssh-user root`，命令不会猜密码、自动换用户或改 SSH 设置。

凭据使用新的本地别名，不覆盖旧文件，不写进报告或 Git。`verify` 检查证据一致性；要判断代码恢复是否正确，还应运行同构建设备结果的 `offline-cross-check`。首次获取与后续离线恢复的命名设备实测和剩余边界见[验收账本](ios-device-support-acceptance.md)。
