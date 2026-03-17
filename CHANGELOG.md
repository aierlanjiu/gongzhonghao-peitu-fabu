# Changelog

本项目遵循语义上接近 Keep a Changelog 的记录方式。

## 2026-03-17

### Added

- 新增技能内置 `scripts/gemini_driver.py`
- 新增技能内置 `scripts/remove_watermark.py`
- 新增水印模板资源 `scripts/assets/bg_48.png` 与 `scripts/assets/bg_96.png`
- 新增 `LICENSE`，采用 MIT 协议
- 新增中文版 `README.md`
- 新增 `scripts/__init__.py`，保证技能内脚本导入更稳
- 新增 README 首页流程图
- 新增 Contributor 标注：`codex`

### Changed

- 将技能定位固定为“输入现成文章后的执行型管线”
- 将 `火焰编辑部老钱` 明确为可选前置项，而非默认步骤
- 将 `generate_images.py` 与 `init_gemini_login.py` 的默认驱动路径改为技能目录内置副本
- 将去水印说明改为技能内 `scripts/remove_watermark.py`
- 调整 `publish_article.py`，优先使用浏览器内 `Meta+V`，系统粘贴仅作兜底
- 更新 `README.md`、`SKILL.md`、`references/setup.md`、`agents/openai.yaml`
- 扩充 `bootstrap_env.sh` 的依赖检查，覆盖 `opencv-python` 与 `numpy`

### Fixed

- 清除仓库中误跟踪的 `.README.md.swp`
- 补齐 `.gitignore`，忽略 `.env`、`.gemini/`、`assets/generated_images/`、`assets/wechat_profile/`、缓存和编辑器临时文件
- 移除 README 中的本机绝对路径泄漏风险
