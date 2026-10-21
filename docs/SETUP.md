# Set up OpenKatana

Use one CLI setup flow with any agent that can run local commands and read files.
OpenKatana does not authenticate an agent, open an OAuth login or start a model.

## From GitHub

Install Python 3.11+ and Git, then run:

```sh
git clone https://github.com/rk0neki/OpenKatana.git
cd OpenKatana
python scripts/setup.py
```

Use `python3` where that is your Python 3.11+ command. The script creates `.venv`,
installs this checkout with its text/vision dependencies, creates
`projects/my-first-film`, and places the included skill in that project's
`.agents/skills/openkatana-video/SKILL.md`. It prints the selected interpreter,
project, runtime status and exact next commands. It preserves an existing valid
project and does not overwrite a customized installed skill.

Choose another project with `--project projects/my-film --name "My film"`.
If dependencies are already installed, add `--skip-install`. `--venv PATH`
selects another Python environment. Existing non-project/non-environment folders
are rejected rather than overwritten.

Setup installs Python dependencies. It does **not** install browsers, FFmpeg,
Blender or model weights, submit generation jobs, upload files or publish work.

## Check the runtime

Install FFmpeg/ffprobe and Chrome/Chromium separately. If needed, point
`OPENKATANA_CHROME` at your browser executable. Blender is optional and can be
selected with `OPENKATANA_BLENDER`. Activate the created environment:

```powershell
# Windows PowerShell
.\.venv\Scripts\Activate.ps1
```

```sh
# Linux/macOS
source .venv/bin/activate
```

Or use `.venv\Scripts\python.exe -m openkatana` on Windows and
`.venv/bin/python -m openkatana` on Linux/macOS, without activation.

```sh
openkatana doctor
openkatana call get_capabilities --workspace projects
openkatana studio projects/my-first-film
```

Open the printed loopback URL. The doctor checks runtime availability, not the
quality of arbitrary scenes or readiness of every optional model workflow.

## Use the skill

Open the project in your agent and tell it to read the installed
`.agents/skills/openkatana-video/SKILL.md`. Agents with project-local skill
discovery can find it automatically; others can read that file explicitly.
Use the environment and workspace reported by setup. Studio's **Agent setup**
dialog contains the same portable instructions for everyone.

For an existing installed package, `openkatana setup --project projects/my-film`
prepares just the project and skill. For manual source installation, create a
virtual environment and run `python -m pip install -e ".[text,vision]"` first.
MCP is optional: install `.[mcp]` and see [the agent guide](AGENT_INTERFACE.md).
CLI calls do not need MCP.
