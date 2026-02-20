"""Integration tests for Docker configuration (4 tests).

These are text-content tests that read the Dockerfile and docker-compose.yml
and verify expected configuration strings.  No Docker daemon is required.
"""

from __future__ import annotations

from pathlib import Path

DOCKERFILE = Path("Dockerfile")
DOCKER_COMPOSE = Path("docker-compose.yml")


class TestDockerConfig:
    """Validate Docker configuration files contain expected settings."""

    def test_dockerfile_has_correct_entrypoint(self) -> None:
        """Dockerfile ENTRYPOINT contains 'python -m cal_ai'."""
        content = DOCKERFILE.read_text()
        assert "python -m cal_ai" in content or 'python", "-m", "cal_ai' in content, (
            "Dockerfile must contain ENTRYPOINT with 'python -m cal_ai'"
        )

    def test_dockerfile_copies_samples(self) -> None:
        """Dockerfile contains a COPY instruction for samples/."""
        content = DOCKERFILE.read_text()
        assert "COPY samples/" in content or "COPY ./samples/" in content, (
            "Dockerfile must COPY samples/ directory into the image"
        )

    def test_docker_compose_mounts_env(self) -> None:
        """docker-compose.yml references .env via env_file or volumes."""
        content = DOCKER_COMPOSE.read_text()
        has_env_file = "env_file" in content and ".env" in content
        has_env_volume = ".env" in content and "volumes" in content
        assert has_env_file or has_env_volume, (
            "docker-compose.yml must include .env in env_file or volumes"
        )

    def test_docker_compose_has_default_command(self) -> None:
        """docker-compose.yml or Dockerfile specifies a default transcript path."""
        # The default command is set in the Dockerfile CMD, which docker-compose
        # inherits.  We check the Dockerfile for CMD with a transcript path.
        dockerfile_content = DOCKERFILE.read_text()
        compose_content = DOCKER_COMPOSE.read_text()

        has_cmd_in_dockerfile = "CMD" in dockerfile_content and "samples/" in dockerfile_content
        has_command_in_compose = "command" in compose_content and "samples/" in compose_content

        assert has_cmd_in_dockerfile or has_command_in_compose, (
            "A default transcript path must be specified via Dockerfile CMD or "
            "docker-compose.yml command"
        )
