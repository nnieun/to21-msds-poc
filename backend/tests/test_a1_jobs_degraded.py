"""보조 표 분석(Docling)이 빠진 채 끝난 작업이 워커 로그에 드러나는지 시험한다."""
from __future__ import annotations

import logging

from msds.preprocess.jobs import run_one, warn_if_degraded


class OneJobStore:
    """run_one이 쓰는 메서드만 둔 작업 저장소."""

    def __init__(self, tmp_path):
        self.job = dict(job_id='job_1', doc_id='doc_1', source_path=str(tmp_path / 'in.pdf'),
                        output_path=str(tmp_path / 'out'), status='queued')
        self.finished = None

    def recover_expired(self):
        return 0

    def claim(self, worker_id, lease_seconds):
        if self.job['status'] != 'queued':
            return None
        self.job['status'] = 'running'
        return dict(self.job)

    def heartbeat(self, job_id, worker_id, lease_seconds):
        return True

    def progress(self, job_id, worker_id, event):
        return True

    def finish(self, job_id, worker_id, *, error=None, result_dir=None):
        self.finished = {'error': error, 'result_dir': result_dir}
        return True


def extractor_returning(meta):
    def extract(source, output, **kwargs):
        output.mkdir(parents=True)
        return meta
    return extract


def test_failed_docling_is_logged_and_job_still_succeeds(tmp_path, caplog):
    store = OneJobStore(tmp_path)
    meta = {'docling_requested': True, 'docling_attempted': True, 'docling_completed': False,
            'docling_error': 'ImportError: undefined symbol: ncclCommResume'}
    with caplog.at_level(logging.WARNING, logger='msds.preprocess.jobs'):
        assert run_one(store, extractor=extractor_returning(meta), use_docling=True)
    assert store.finished == {'error': None, 'result_dir': str(tmp_path / 'out')}
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert 'job_1' in warnings[0].getMessage() and 'ncclCommResume' in warnings[0].getMessage()


def test_completed_or_skipped_docling_is_not_logged(caplog):
    with caplog.at_level(logging.WARNING, logger='msds.preprocess.jobs'):
        assert not warn_if_degraded('job_1', {'docling_attempted': True, 'docling_completed': True})
        assert not warn_if_degraded('job_1', {'docling_attempted': False, 'docling_completed': False})
        assert not warn_if_degraded('job_1', None)
    assert not caplog.records
