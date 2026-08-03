# Operations documents

로컬 실행, 검증, 배포 준비와 문제 해결 문서의 인덱스다.

- [Demo runbook](demo-runbook.md)
- [Release checklist](release-checklist.md)
- [Release gate report](release-gate-report.md)
- [Production environment completion](production-environment-completion-runbook.md)
- [DevSpace workflow](devspace-workflow.md)
- [Troubleshooting](troubleshooting.md)

## 캐시와 생성물 정리

대상 확인:

```bash
python3 scripts/clean_local_artifacts.py --dry-run
```

실제 삭제:

```bash
python3 scripts/clean_local_artifacts.py
```

이 명령은 `.venv`, `node_modules`, Dataset fixture와 문서 캡처를 삭제하지 않는다.

