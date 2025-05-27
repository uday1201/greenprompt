

# Contributing to GreenPrompt

Thank you for your interest in contributing to GreenPrompt! We welcome contributions from the community.

## How to Contribute

1. **Fork the repository** on GitHub.  
2. **Clone your fork**:
   ```bash
   git clone https://github.com/yourusername/greenprompt.git
   cd greenprompt
   ```
3. **Create a new branch** for your feature or bugfix:
   ```bash
   git checkout -b feature/my-new-feature
   ```
4. **Install dependencies** and set up the environment:
   ```bash
   poetry install
   ```
5. **Make your changes** and ensure code is linted and formatted:
   ```bash
   poetry run ruff check .
   poetry run ruff fmt .
   ```
6. **Add tests** for new functionality and run existing tests:
   ```bash
   pytest
   ```
7. **Commit your changes** following [Conventional Commits](https://www.conventionalcommits.org/) style:
   ```bash
   git commit -m "feat(cli): add new `stop` command"
   ```
8. **Push your branch** to your fork:
   ```bash
   git push origin feature/my-new-feature
   ```
9. **Open a Pull Request** on the main repository, describing your changes and referencing any related issues.

## Code Review

- We strive for timely reviews; maintainers will review your PR promptly.  
- Address review comments by updating your branch as needed.

## Reporting Issues

If you encounter bugs or have feature requests, please open an issue using the provided templates (`.github/ISSUE_TEMPLATE/`).  