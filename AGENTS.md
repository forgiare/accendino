# AGENTS.md

This file provides guidance to AI assistants when working with code in this repository.

## What is this project ?

_Accendino_ is a Python build-orchestration tool: it reads a Python-syntax "accendino file" describing a
DAG of build artifacts (each with git/local/archive sources, platform package dependencies, and
prepare/build commands via cmake/meson/autotools/qmake/custom commands), then checks out sources,
installs missing OS packages, and builds everything in dependency order. It was originally built to
deploy the [Ogon](https://github.com/ogon-project) RDP server stack but is generic.

## Commands

```console
# dev install
python3 -m venv _v && source _v/bin/activate
pip install -e .

# run the built CLI
accendino [options] <accendino-file>          # e.g. accendino --targets=ogon ogon.accendino

# run tests (unittest-based, not wired into CI)
python -m pytest tests/
# or
python -m unittest discover tests

# lint (pylint config lives in .pylintrc: camelCase enforced, 150 col limit)
pylint src/accendino
```

There is no compiled build step for accendino itself — `pip install .` / `pip install -e .` via
`pyproject.toml` (setuptools) is the whole build. CI (`.github/workflows/ci-github.yml`,
`ci-windows.yml`) doesn't run the unit tests; it exercises the tool end-to-end by actually building
real targets (ogon, forgiare, freerdp3) on Linux/mingw/Windows matrices.

## Architecture

Everything lives under `src/accendino/`:

- **`main.py`** — CLI entry point (`accendino = accendino.main:main`). `AccendinoConfig` holds all
  run state and, critically, the `exec()` sandbox (`self.context` dict) that accendino source files run
  in — it's how `ARTIFACTS`, `DEFAULT_TARGETS`, `include()`, `getOption()`, `checkDistrib()`, etc. get
  injected into `.accendino` files as if they were builtins. `run()` drives the whole pipeline: parse
  args → detect platform → pick a toolchain → read source file(s) → `finalizeConfig()` → build a
  topologically-ordered `buildPlan` from requested `targets` → check/install platform packages → for
  each artifact: `init()` → `checkout()` → `prepare()` → `build()`.
- **`builditems.py`** — the artifact class hierarchy: `DepsBuildArtifact` (base, meta-only, no
  source/build) → `BuildArtifact` (generic prepare_cmds/build_cmds) → `CMakeBuildArtifact`,
  `MesonBuildArtifact`, `QMakeBuildArtifact`, `AutogenBuildArtifact`, `CustomCommandBuildArtifact`.
  Build state is cached on disk per artifact via two marker files in the artifact's build dir:
  `accendino.prepared` (pickled `BuildStepDump` of env+commands, compared to detect drift) and
  `accendino.built`. `needsRebuildFromDepsUpdates()` cascades rebuilds to dependents by comparing
  `builtFile` mtimes. `--refreshSources` drops these markers when `GitSource.checkout()` detects the
  upstream actually moved; `--refresh` (`AccendinoConfig.refresh`) unconditionally drops them for the
  explicitly requested targets via `BuildArtifact.forceRebuild()`.
- **`sources.py`** — `Source` subclasses (`GitSource`, `LocalSource`, `RemoteArchiveSource`) that know
  how to populate an artifact's source directory and report whether they actually changed it
  (`self.refreshed`), which feeds the rebuild-cascade logic above.
- **`toolchain.py`** — `IToolChain` subclasses (`GccToolChain`, `ClangToolChain`, `MingwToolChain`,
  `VsToolChain`, `DefaultToolChain`) abstract compiler selection/activation and platform package
  requirements per toolchain. `DefaultToolChain` autodetects by probing which toolchain's required
  packages are satisfiable.
- **`localdeps.py`** — `PackageManagerBase` subclasses per OS package manager (`dpkg`, `rpm`, `pacman`,
  `pkg`, `chocolatey`, `brew`, msys2); `getPkgManager()` picks one from the detected distro.
- **`utils.py`** — cross-cutting helpers: `NativePath`/`RunInShell` (path/shell abstractions for
  posix/windows/msys2), `DepsAdjuster`/`ConditionalDep` (conditional dep injection based on platform
  version), `checkVersionCondition`/`checkAccendinoVersion` (the `<op> <distrib> <version>` mini
  language), `treatPackageDeps`/`mergePkgDeps`.
- **`pocket/*.accendino`** — the built-in library of reusable accendino files for common dependencies
  (zlib, openssl, ffmpeg, wayland, sdl2/3, freerdp, fido2, ...), searched via `ACCENDINO_PATH` env var
  then this pocket dir. Top-level `*.accendino` files (`ogon.accendino`, `forgiare.accendino`,
  `weston.accendino`) are example/real "root" build definitions that `include()` pocket files.

An accendino file is plain Python `exec()`'d with a curated set of injected names (see
`AccendinoConfig.__init__`'s `self.context` dict in `main.py`, and MANUAL.md for the full list of
variables/functions/objects available to source files) — there's no separate DSL parser.

## Platform package dependency syntax

Package deps are `Dict[str, List[str]]` keyed by distro match strings supporting `|` (OR) and
`<distrib>-><targetDistrib>@<arch>` (cross-compile) forms, e.g. `'Ubuntu|Debian'`,
`'Fedora->mingw@x86_64'`. Windows package names are `<choco|path>/<name>`. See MANUAL.md
("Platform packages dependencies") for the full grammar — this is the part most `.accendino` files
spend their logic on.

## Conventions

- Method/function naming is camelCase (enforced by `.pylintrc`), not snake_case — this diverges from
  typical PEP 8 and is intentional throughout the codebase.
- `CHANGELOG.md` is organized by version section (`## X.Y.Z`); when adding a changelog entry for
  unreleased work, check whether the top section is already an actual release commit before assuming
  it's safe to edit — this repo's history is sometimes deliberately rewritten to fold doc/changelog
  entries into the release-bump commit rather than leaving a trailing "Unreleased" section.
