# Operations documents

로컬 실행, 검증, 배포 준비와 문제 해결 문서의 인덱스다.

- [Demo runbook](demo-runbook.md)
- [Release checklist](release-checklist.md)
- [Predictive Maintenance v3.1 release runbook](predictive-maintenance-v3.1-release-runbook.md)
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

이 명령은 `.venv`, `node_modules`, 실행 중인 Vite dependency cache, Dataset fixture와 문서 캡처를 삭제하지 않는다.

Vite dependency cache까지 초기화해야 할 때만 프론트 서버를 먼저 종료하고 다음 명령을 사용한다.

```bash
python3 scripts/clean_local_artifacts.py --include-runtime-caches
```

이 옵션을 사용한 뒤에는 프론트 서버를 반드시 재시작한다. 실행 중인 Vite cache를 삭제하면 `504 Outdated Optimize Dep`로 흰 화면이 발생할 수 있다.

