# 项目代理协作规范

## Git 提交要求

- 创建提交前，必须检查仓库当时实际生效的 commitlint、Git hooks 和相关 package scripts，不得根据经验臆造提交格式。
- 检查范围至少包括 `commitlint.config.*`、`.commitlintrc*`、`package.json`、`.husky/`、`.git/hooks/`、`core.hooksPath` 和 `pre-commit` 配置（存在时）。
- 仓库规则优先于文档示例；未配置 Conventional Commits 时，不得把示例格式当成强制规则。
- 提交标题和正文必须使用中文，内容详细、专业，并准确说明变更范围、关键行为和验证结果。
- 未经用户明确授权，不得使用 `--no-verify` 绕过提交校验。
