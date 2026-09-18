# Android Tool Suite 发布中心

这是 Android Tool Suite 的官方更新索引与发布目录。GitHub Pages 同时展示宿主 APK 和官方插件包，并允许在正式版及其历史版本之间选择。仓库只保存索引生成器、组织仓库发现规则、公钥和静态展示页；应用与插件二进制仍由各自的 GitHub Release 发布。

## 正式发布目录

- `release/index-v1.json`：正式通道。应用读取正式版宿主和各插件最新的非预发布 Release。
- `release/catalog-v1.json`：宿主和插件的全部正式历史版本，供 Pages 与应用内版本选择使用。
- `index-v1.json`：正式通道的兼容地址，供旧版应用继续使用。

最新索引和历史目录都使用同一把 ECDSA 私钥签名，签名位于相同目录下对应的 `.sig` 文件。宿主从最新索引检查应用和插件更新，同时读取历史目录提供插件版本选择，并在下载前校验签名、资产大小和 SHA-256；自动更新仍只指向最新版本。

插件 `release-metadata.json` 可以携带 `dataCompatibility`，声明本版本写入的数据格式以及可读取范围。生成器验证后将声明写入历史目录；旧 Release 缺少声明时按数据格式 `v0` 处理，新版可通过把最小可读版本声明为 `0` 来承接旧数据。

## 事件驱动更新

本仓库不再定时轮询组件仓库。应用或插件工作流完成发布后，通过 GitHub `repository_dispatch` 发送 `component_published` 事件；本仓库随后重新生成正式最新索引与历史目录并部署 GitHub Pages。短时间内的多个事件由 Actions 并发组自动合并，最终部署最新状态。

各组件仓库通过组织 GitHub App `android-tool-suite-registry-app` 创建短时 installation token。组织变量 `REGISTRY_APP_CLIENT_ID` 和 Secret `REGISTRY_APP_PRIVATE_KEY` 只开放给 `app` 与四个插件仓库；App 仅安装到 `plugin-registry`，并只具有 Contents 写权限。任务结束后令牌自动撤销，不把凭据写入产物或日志。

若事件发送失败，可在 Actions 页面手动运行 `Build and deploy signed registry`。这是一条恢复路径，不需要重新发布组件。

## 插件如何进入目录

插件仓库名称需要以 `plugin-` 开头。日常 CI 只测试并上传构建产物；维护者推送 `v<versionName>` 标签并成功发布后，工作流向本仓库发送更新事件。组织内符合发现规则的插件会自动进入正式目录，不需要手工修改 `sources.json`。

生成器只接受非草稿、非预发布且标签匹配产品版本的正式 Release，严格校验元数据与交付资产。远程 Debug 发布、调试目录及旧调试标签格式均不支持，也不生成兼容端点。

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

生成最新索引与历史目录需要访问 GitHub API；可选的 `GITHUB_TOKEN` 能提高 API 限额：

```powershell
python scripts/build-registry.py `
  --sources sources.json `
  --channel release `
  --output public/release/index-v1.json `
  --catalog-output public/release/catalog-v1.json
```

签名验证示例：

```powershell
openssl dgst -sha256 -verify registry-public.pem `
  -signature public/release/index-v1.json.sig `
  public/release/index-v1.json
```
