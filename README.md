# Android Tool Suite 插件仓库

这是 Android Tool Suite 的官方更新索引与插件目录。仓库只保存索引生成器、组织仓库发现规则、公钥和静态展示页；应用与插件二进制仍由各自的 GitHub Release 发布。

## 两个发布通道

- `release/index-v1.json`：正式通道。应用读取正式版宿主和各插件最新的非预发布 Release。
- `debug/index-v1.json`：调试通道。读取组织内所有 `plugin-*` 仓库的 `debug` 预发布；适合联调刚推送并已通过 CI 的插件。
- `index-v1.json`：正式通道的兼容地址，供旧版应用继续使用。

两个索引都使用同一把 ECDSA 私钥签名，签名分别位于同目录下的 `index-v1.json.sig`。宿主内置 `registry-public.pem` 对应的公钥，并在下载插件前继续校验索引签名、资产大小和 SHA-256。

## 事件驱动更新

本仓库不再定时轮询组件仓库。应用或插件工作流完成发布后，通过 GitHub `repository_dispatch` 发送 `component_published` 事件；本仓库随后重新生成两个索引并部署 GitHub Pages。短时间内的多个事件由 Actions 并发组自动合并，最终部署最新状态。

各组件仓库通过组织 GitHub App `android-tool-suite-registry-app` 创建短时 installation token。组织变量 `REGISTRY_APP_CLIENT_ID` 和 Secret `REGISTRY_APP_PRIVATE_KEY` 只开放给 `app` 与三个插件仓库；App 仅安装到 `plugin-registry`，并只具有 Contents 写权限。任务结束后令牌自动撤销，不把凭据写入产物或日志。

若事件发送失败，可在 Actions 页面手动运行 `Build and deploy signed registry`。这是一条恢复路径，不需要重新发布组件。

## 调试插件如何进入目录

插件仓库名称需要以 `plugin-` 开头。推送 `main` 后，组件 CI 会：

1. 完成测试并构建调试 `.atsplugin`；
2. 更新名为 `debug` 的公开预发布及其 `release-metadata.json`；
3. 向本仓库发送更新事件。

因此新插件不需要手工修改 `sources.json`；只要位于 Android Tool Suite 组织、仓库名符合规则、CI 成功并生成规范的 `debug` 预发布，就会自动出现在调试目录。正式目录仍只读取规范的 `v<versionName>` 正式 Release。

宿主的插件仓库页面也保留“导入本地插件包”入口，用于不推送远程的本地联调。它属于本地导入信任路径，不会伪装成已通过仓库签名校验的插件。

## 仓库设置

1. 在 Actions Secret 中创建 `REGISTRY_SIGNING_KEY_PEM`，内容为与 `registry-public.pem` 匹配的私钥。
2. 在 Settings → Pages 中选择 GitHub Actions 作为部署来源。
3. 创建并安装上文所述的 GitHub App，为组件仓库提供 `REGISTRY_APP_CLIENT_ID` 和 `REGISTRY_APP_PRIVATE_KEY`。

集成工作区把本仓库作为 `plugin-registry/` 子模块锁定；索引生成器测试也会进入外层 `tools/build-all.ps1` 的正式验收流程。运行时索引仍由本仓库自己的 Pages 工作流发布，外层 gitlink 不参与在线更新。

私钥和 dispatch token 都不得提交到 Git。

## 本地验证

生成器单元测试不访问网络：

```powershell
python -m unittest discover -s tests -v
```

生成两个索引需要访问 GitHub API；可选的 `GITHUB_TOKEN` 能提高 API 限额：

```powershell
python scripts/build-registry.py `
  --sources sources.json `
  --channel release `
  --output public/release/index-v1.json
python scripts/build-registry.py `
  --sources sources.json `
  --channel debug `
  --output public/debug/index-v1.json
```

签名验证示例：

```powershell
openssl dgst -sha256 -verify registry-public.pem `
  -signature public/release/index-v1.json.sig `
  public/release/index-v1.json
```
