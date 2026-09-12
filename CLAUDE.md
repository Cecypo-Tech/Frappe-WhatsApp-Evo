## Skill routing

When the user's request matches an available skill, invoke it via the Skill tool. When in doubt, invoke the skill.

Key routing rules:
- Architecture → invoke /plan-eng-review
- Bugs/errors → invoke /investigate
- QA/testing site behavior → invoke /qa or /qa-only
- Code review/diff check → invoke /review
- Ship/deploy/PR → invoke /ship or /land-and-deploy
- Author a backlog-ready spec/issue → invoke /spec
- Save progress → invoke /context-save
- Resume context → invoke /context-restore
