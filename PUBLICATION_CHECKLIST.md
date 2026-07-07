# Public Repository Checklist

Use this checklist before publishing the repository.

## Keep

```text
backend/
desktop/
scripts/
tools/              only source files or setup instructions
README.md
DESIGN.md
README_RUN_WINDOWS.md
RELEASE_NOTES.md
requirements.txt
VERSION
.gitignore
.gitattributes
```

## Exclude

```text
.venv/
venv/
models/
downloads/
storage/
temp/
debug/
__pycache__/
*.wav
*.mp3
*.mp4
*.log
*.db
.env
```

## Final manual check

Before publishing, search the full repository for private data, local machine paths, account names, credentials, personal examples, generated outputs, and internal development notes. Remove or rewrite anything that is not meant for public viewing.
