# NL2Repo-Bench Licence and IP Note

**Date**: 2026-10-11
**Task**: T011 (User Story 7, ruling R2)
**Evaluated Subject**: `multimodal-art-projection/NL2RepoBench` and arXiv:2512.12730

---

## 1. Sources Checked

On 2026-10-11, the following four authoritative sources were inspected:

1. **GitHub API License Field**:
   - Query: `gh api repos/multimodal-art-projection/NL2RepoBench --jq '{license: .license, default_branch: .default_branch}'`
   - Result: `{"default_branch": "main", "license": null}`. No licence is declared or registered with GitHub.

2. **Repository Root Directory Listing**:
   - Query: `gh api repos/multimodal-art-projection/NL2RepoBench/contents --jq '.[].name'`
   - Result: Files present are `.DS_Store`, `__init__.py`, `config.json`, `docker_self`, `logging_config.py`, `main.py`, `only_test.py`, `openhands`, `readme.md`, `requirements.txt`, `template`, `test_data_service.py`, `test_files`, `tests`, `workspaces`.
   - Observation: No `LICENSE`, `COPYING`, or `LICENCE` file exists anywhere in the repository root.

3. **Repository README (`readme.md`)**:
   - Query: Checked full text of `readme.md`.
   - Result: Contains zero occurrences of "license" or "copyright". No terms of use, grant of rights, or redistribution permissions are stated.

4. **Academic Paper Abstract Page (arXiv:2512.12730)**:
   - Query: Inspected `https://arxiv.org/abs/2512.12730`.
   - Result: Paper text carries the standard arXiv non-exclusive distribution licence (`http://arxiv.org/licenses/nonexclusive-distrib/1.0/`). No dataset or code licence statement is provided on the paper page.

---

## 2. Findings and Conclusion

1. **No Grant to Copy**: The upstream dataset authors have not provided any open-source or permissive licence grant covering the requirement documents or test suites.
2. **Upstream Copyright Retained**: In the absence of an explicit grant, default copyright laws apply. The authors retain all exclusive rights to their text and benchmark documents. Each underlying upstream target project also maintains its own distinct licence.
3. **Repository Public Policy**: Kroker is a public repository with strict intellectual property and licensing standards. Importing unlicenced requirements or assets would create unacceptable copyright exposure.

---

## 3. Decision (Ruling R2)

**Decision: Nothing imported.**

In accordance with ruling R2, no case, requirement document, oracle, or benchmark asset from `multimodal-art-projection/NL2RepoBench` is imported into Kroker.

Verification confirmed via `git status` and `git diff --stat c3f6319c..HEAD -- benchmarks`: this branch adds zero files originating from `NL2RepoBench`.
