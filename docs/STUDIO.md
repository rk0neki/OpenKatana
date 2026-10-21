# OpenKatana Studio

Studio is the local workspace for human direction, agent-authored edits and final
review. It opens in a browser, requires no OpenKatana account and uses no embedded
AI service. A separate agent with local file and terminal access runs the tools.

## Start together

Follow [setup](SETUP.md), then run `openkatana studio projects/my-first-film`.
Open the printed loopback URL.

**Start → Set up your agent** provides one portable GitHub/CLI setup prompt.
It runs `python scripts/setup.py`, installs the included skill into the project,
and asks the agent to check dependencies before editing. The same instructions
work with any agent that has terminal and file access. CLI is the default;
MCP remains optional. No platform-specific account connector is provided.

Copying a prompt does not establish a connection or launch an agent. The agent
confirms its own readiness. Setup does not authorize paid jobs, model downloads,
uploads or publishing.

## Four focused views

- **Start:** the setup entry point, three-step workflow and eight capability groups.
- **Studio:** three numbered steps: **Brief & media**, **Preview & refine**,
  and **Render & review**. Describe the film beside its preview, attach media,
  then copy the brief to your agent. Select a shot or expand **Adjust the edit**
  for shot controls, soundtrack and image workflows. **Build a first cut**
  and **Timeline source** are optional disclosures. The step buttons jump to
  each section; render controls sit in the final step.
- **Tools:** a searchable, categorized inventory of the actual CLI/MCP catalog.
  Each large tool card opens its Markdown guide with a click or Enter/Space.
  The separate parameter disclosure and Add to brief action remain independent.
  **Add to brief** requests agent use of a tool; it does not execute that tool.
- **Review:** recorded render jobs, video playback/download and human verdicts.

Advanced 3D, HDR, model processing and custom composition tools are discoverable
in the library and invoked by the agent/CLI. A library entry does not imply that
every dependency/model is installed or that it has a dedicated graphical editor.

## Working in the same project

The brief includes the current workspace, project ID, revision and imported media
inventory. Copy it to the agent, or download it as Markdown. Brief drafts are
stored in this browser, per project. Nothing is automatically sent to an AI.

Studio checks saved project state every four seconds while the page is visible.
External changes load automatically when there is no unsaved edit and preview
playback is idle. If the human has unsaved changes, Studio shows a conflict notice
and preserves the original revision. A stale save is rejected by the server.
Loading the saved version requires confirming the discard of unsaved timeline
changes. The written brief is retained. A hidden tab resumes checks when visible.

Large clips over 64 MB should be imported by the agent/CLI; the browser upload
path is intentionally limited. Preview frames are silent; review audio in the
rendered MP4. Imported clips use their first frame for the basic Images panel;
whole-clip processing is available in the tool library.

## Reading guides

The guide body scrolls independently. Copy, Download .md and Close remain in
the fixed header on desktop and narrow layouts. Copy and Download include the
complete guide, regardless of scroll position. Downloads have portable filenames.

The Start page links to the GitHub repository and has no project resume bar or
permanent status footer. Action feedback appears in a dismissible notification;
errors remain visible until dismissed or replaced by the next action.

## Interface and distribution

Studio uses local HTML, CSS, JavaScript and OpenKatana branding, included in the
wheel/source bundle. It is a loopback-only, single-user application. Nothing is
automatically sent to an AI service.

Local MCP setup is available from Agent setup. It does not require a hosted app.
See [hosting options](HOSTING.md) for the separate requirements of remote access.

## Verification

`python scripts/test_studio_live.py --out work/studio-check-NEW` exercises an
isolated project: onboarding, full tool discovery, guide reading, import,
planning, editing, revision conflicts, agent refresh, a real local render and
390px responsive layouts. It also checks cross-origin write/invalid-host rejection
and bundled asset serving. This test uses existing Chrome/FFmpeg, no models or
provider jobs. Screenshots and a JSON result are written under the chosen folder.
