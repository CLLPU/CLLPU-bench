import json
import os
import subprocess
import tomllib
from pathlib import Path

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name


RUNTIME_ROOT = Path(__file__).resolve().parents[1]
ROOT = RUNTIME_ROOT.parent
LANGUAGES = {"ar", "bn", "de", "en", "es", "fr", "ja", "sw", "th", "zh"}


def test_active_runtime_is_grouped_under_one_directory():
    for name in ("configs", "evaluation", "scripts", "src", "tests"):
        assert (RUNTIME_ROOT / name).is_dir()
        assert not (ROOT / name).exists()


def test_packaged_python_scripts_have_portable_shebangs():
    for path in sorted((RUNTIME_ROOT / "scripts").glob("*.py")):
        first_line = path.read_text(encoding="utf-8").splitlines()[0]
        assert first_line == "#!/usr/bin/env python3", f"Missing Python shebang: {path}"


def test_no_large_runtime_directories_are_copied():
    for name in ("saves", "model", "models", "wandb", "logs"):
        assert not (ROOT / name).exists()


def test_core_model_package_is_not_git_ignored():
    required = (
        RUNTIME_ROOT / "src/cllpu/model/__init__.py",
        RUNTIME_ROOT / "configs/model/Llama-3.1-8B-Instruct.yaml",
    )
    for path in required:
        result = subprocess.run(
            ["git", "check-ignore", "--quiet", str(path)],
            cwd=ROOT,
            check=False,
        )
        assert result.returncode == 1, f"Required release file is ignored: {path}"


def test_distribution_declares_every_user_facing_workflow_script():
    metadata = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    declared = set(metadata["tool"]["setuptools"]["script-files"])
    expected = {
        str(path.relative_to(ROOT))
        for path in (RUNTIME_ROOT / "scripts").iterdir()
        if path.suffix in {".py", ".sh"}
    }
    assert declared == expected


def test_requirements_contains_only_declared_user_dependencies():
    metadata = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    project = metadata["project"]
    selected_extras = ("gpu", "flash", "tracking", "embedding", "mia", "belebele")
    expected_requirements = list(project["dependencies"])
    for extra in selected_extras:
        expected_requirements.extend(project["optional-dependencies"][extra])
    expected = {
        canonicalize_name(Requirement(value).name) for value in expected_requirements
    }

    requirement_lines = [
        line.strip()
        for line in (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith(("#", "-"))
    ]
    actual = {canonicalize_name(Requirement(value).name) for value in requirement_lines}

    assert actual == expected


def test_reviewed_release_dataset_is_complete_and_trackable():
    data_root = RUNTIME_ROOT / "data/multilingual"
    files = sorted(data_root.rglob("*.jsonl"))
    assert len(files) == 72
    unexpected = [
        path for path in data_root.rglob("*") if path.is_file() and path.suffix != ".jsonl"
    ]
    assert not unexpected
    assert max(path.stat().st_size for path in files) < 100 * 1024 * 1024

    for relative_path in (
        "runtime/data/multilingual/qa_flat.en.jsonl",
        "runtime/data/multilingual/train_splits/eval_common_plus_culture_all.jsonl",
    ):
        result = subprocess.run(
            ["git", "check-ignore", "--quiet", relative_path],
            cwd=ROOT,
            check=False,
        )
        assert result.returncode == 1, f"Release data is ignored: {relative_path}"


def _jsonl_protocol_values(path: Path):
    count = 0
    languages = set()
    roles = set()
    variants = set()
    origins = set()
    families = set()
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            record = json.loads(line)
            count += 1
            languages.add(record["language"])
            roles.add(record["topic_role"])
            variants.add(record["variant_layer"])
            if "culture_origin" in record:
                origins.add(record["culture_origin"])
            if "dataset_family" in record:
                families.add(record["dataset_family"])
    return count, languages, roles, variants, origins, families


def test_screening_and_full_evaluation_data_match_protocol():
    data_root = RUNTIME_ROOT / "data/multilingual"
    for language in sorted(LANGUAGES):
        values = _jsonl_protocol_values(data_root / f"qa_flat.{language}.jsonl")
        count, languages, roles, variants, _, _ = values
        assert count == 4000
        assert languages == {language}
        assert roles == {"target", "neighbor"}
        assert variants == {"core", "surface"}

    culture_counts = {"ar": 2640, "bn": 2160}
    monitor_counts = {"ar": 264, "bn": 216}
    culture_root = data_root / "train_splits/culture_origin"
    for origin in sorted(LANGUAGES):
        monitor_path = culture_root / f"{origin}_source_monitor_core_surface.jsonl"
        values = _jsonl_protocol_values(monitor_path)
        count, languages, roles, variants, origins, families = values
        assert count == monitor_counts.get(origin, 240)
        assert languages == {origin}
        assert roles == {"target", "neighbor"}
        assert variants == {"core", "surface"}
        assert origins == {origin}
        assert families == {"culture_specific"}

        path = culture_root / f"{origin}_eval_all_languages_core_surface.jsonl"
        count, languages, roles, variants, origins, families = _jsonl_protocol_values(path)
        assert count == culture_counts.get(origin, 2400)
        assert languages == LANGUAGES
        assert roles == {"target", "neighbor"}
        assert variants == {"core", "surface"}
        assert origins == {origin}
        assert families == {"culture_specific"}


def test_sweep_dry_run_uses_public_entrypoint_and_target_model():
    result = subprocess.run(
        [
            "bash",
            "runtime/scripts/run_multilingual_unlearn_sweep.sh",
            "--dry-run",
            "--finetuned-model",
            "example/target-model",
            "--methods",
            "ga",
            "--learning-rates",
            "1e-5",
            "--train-eval",
            "false",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    assert "-m cllpu.train" in result.stdout
    assert "target_model=example/target-model" in result.stdout


def test_culture_sweep_defaults_source_language_to_origin():
    monitor_counts = {"ar": 264, "bn": 216}
    training_counts = {"ar": 33, "bn": 27}
    for origin in sorted(LANGUAGES):
        result = subprocess.run(
            [
                "bash",
                "runtime/scripts/run_multilingual_culture_origin_unlearn_sweep.sh",
                "--culture-origin",
                origin,
                "--finetuned-model",
                "example/target-model",
                "--methods",
                "ga",
                "--learning-rates",
                "1e-5",
                "--train-eval",
                "false",
                "--dry-run",
            ],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        expected_monitor = monitor_counts.get(origin, 240)
        expected_training = training_counts.get(origin, 30)
        assert f"multilingual_culture_origin={origin}" in result.stdout
        assert f"multilingual_source_language={origin}" in result.stdout
        assert f"multilingual_culture_forget_expected_count={expected_training}" in result.stdout
        assert f"multilingual_culture_retain_expected_count={expected_training}" in result.stdout
        assert (
            f"multilingual_culture_monitor_expected_count={expected_monitor}"
            in result.stdout
        )


def test_sweep_can_select_exactly_one_method():
    result = subprocess.run(
        [
            "bash",
            "runtime/scripts/run_multilingual_unlearn_sweep.sh",
            "--dry-run",
            "--finetuned-model",
            "example/target-model",
            "--methods",
            "simnpo",
            "--learning-rates",
            "1e-5",
            "--simnpo-betas",
            "3.5",
            "--simnpo-gammas",
            "0.125",
            "--simnpo-deltas",
            "1",
            "--train-eval",
            "false",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    commands = [line for line in result.stdout.splitlines() if "cllpu.train" in line]
    assert len(commands) == 1
    assert "trainer=SimNPO" in commands[0]
    for other in ("GradAscent", "GradDiff", "NPO", "DrNPO", "DrSimNPO"):
        assert f"trainer={other}" not in commands[0]


def test_common_sweep_defaults_match_paper_grid():
    result = subprocess.run(
        [
            "bash",
            "runtime/scripts/run_multilingual_unlearn_sweep.sh",
            "--dry-run",
            "--finetuned-model",
            "example/target-model",
            "--methods",
            "npo,simnpo,drnpo,drsimnpo",
            "--train-eval",
            "false",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    commands = [line for line in result.stdout.splitlines() if "cllpu.train" in line]
    by_trainer = {
        trainer: [line for line in commands if f"trainer={trainer}" in line]
        for trainer in ("NPO", "SimNPO", "DrNPO", "DrSimNPO")
    }

    assert {trainer: len(lines) for trainer, lines in by_trainer.items()} == {
        "NPO": 6,
        "SimNPO": 12,
        "DrNPO": 12,
        "DrSimNPO": 24,
    }
    assert all("trainer.method_args.beta=0.05" not in line for line in commands)
    assert {token for line in by_trainer["NPO"] for token in line.split() if token.startswith("trainer.method_args.beta=")} == {
        "trainer.method_args.beta=0.1",
        "trainer.method_args.beta=0.5",
    }
    assert all("trainer.method_args.delta=1" in line for line in by_trainer["SimNPO"])
    assert all("trainer.method_args.delta=1" in line for line in by_trainer["DrSimNPO"])
    assert {token for line in by_trainer["DrNPO"] for token in line.split() if token.startswith("trainer.method_args.beta_dv_forget=")} == {
        "trainer.method_args.beta_dv_forget=2",
        "trainer.method_args.beta_dv_forget=5",
    }
    assert {token for line in by_trainer["DrSimNPO"] for token in line.split() if token.startswith("trainer.method_args.sigma_forget=")} == {
        "trainer.method_args.sigma_forget=2",
        "trainer.method_args.sigma_forget=5",
    }


def test_skip_existing_requires_success_marker_with_matching_command(tmp_path):
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_python = fake_bin / "python"
    fake_python.write_text(
        "#!/usr/bin/env bash\nprintf '%s\\n' \"$PWD\" > \"$SWEEP_PWD_FILE\"\nexit 0\n",
        encoding="utf-8",
    )
    fake_python.chmod(0o755)
    sweep_pwd_file = tmp_path / "sweep-pwd.txt"
    output_root = tmp_path / "runs"
    command = [
        "bash",
        "runtime/scripts/run_multilingual_unlearn_sweep.sh",
        "--finetuned-model",
        "example/target-model",
        "--methods",
        "ga",
        "--learning-rates",
        "1e-5",
        "--train-eval",
        "false",
        "--output-root",
        str(output_root),
    ]
    env = {
        **os.environ,
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
        "SWEEP_PWD_FILE": str(sweep_pwd_file),
    }
    subprocess.run(command, cwd=ROOT, env=env, check=True, capture_output=True, text=True)
    assert sweep_pwd_file.read_text(encoding="utf-8").strip() == str(ROOT)
    markers = list(output_root.glob("*/.crosslingual_run_complete"))
    assert len(markers) == 1

    skipped = subprocess.run(
        [*command, "--skip-existing"],
        cwd=ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    assert "Skipping completed run with matching command" in skipped.stderr

    markers[0].write_text("different-protocol\n", encoding="utf-8")
    mismatch = subprocess.run(
        [*command, "--skip-existing"],
        cwd=ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert mismatch.returncode != 0
    assert "incomplete or protocol-mismatched" in mismatch.stderr


def test_skip_existing_fingerprint_covers_external_data_and_config_roots(tmp_path):
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_python = fake_bin / "python"
    fake_python.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    fake_python.chmod(0o755)
    output_root = tmp_path / "runs"
    command = [
        "bash",
        "runtime/scripts/run_multilingual_unlearn_sweep.sh",
        "--finetuned-model",
        "example/target-model",
        "--methods",
        "ga",
        "--learning-rates",
        "1e-5",
        "--train-eval",
        "false",
        "--output-root",
        str(output_root),
    ]
    base_env = {**os.environ, "PATH": f"{fake_bin}:{os.environ['PATH']}"}
    first_env = {
        **base_env,
        "CROSS_LINGUAL_DATA_DIR": str(tmp_path / "data-a"),
        "CROSS_LINGUAL_CONFIG_DIR": str(RUNTIME_ROOT / "configs"),
    }
    subprocess.run(command, cwd=ROOT, env=first_env, check=True, capture_output=True, text=True)

    changed_data = subprocess.run(
        [*command, "--skip-existing"],
        cwd=ROOT,
        env={**first_env, "CROSS_LINGUAL_DATA_DIR": str(tmp_path / "data-b")},
        check=False,
        capture_output=True,
        text=True,
    )
    assert changed_data.returncode != 0
    assert "protocol-mismatched" in changed_data.stderr

    changed_config = subprocess.run(
        [*command, "--skip-existing"],
        cwd=ROOT,
        env={**first_env, "CROSS_LINGUAL_CONFIG_DIR": str(tmp_path / "configs-b")},
        check=False,
        capture_output=True,
        text=True,
    )
    assert changed_config.returncode != 0
    assert "protocol-mismatched" in changed_config.stderr
