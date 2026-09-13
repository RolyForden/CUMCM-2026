#!/usr/bin/env bash
# 自动批准 PreToolUse 权限请求（用户显式要求，避免逐次手动点击）。
# 该脚本从 stdin 读取工具调用 JSON，输出统一的 allow 决策。
# 用途仅限本项目；项目冻结规则（不修改 data/raw/、不改正式结果）由
# settings.local.json 中的 deny 规则另行保障，不依赖本脚本。
cat <<'JSON'
{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"allow","permissionDecisionReason":"auto-approved: user requested no manual approvals for this session"}}
JSON
