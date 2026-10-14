"""Opt-in nonblocking external trigger hooks for the existing sales Scheduler.

Business dates, retries and publication checks belong to the external runner.
No hook is enabled unless a local config explicitly opts in.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess


class ExternalDailyJobs:
    def __init__(self):
        self.children = {}

    def tick(self, log, *, config_path=None, dry_run=False):
        path = config_path or os.environ.get('SCHEDULER_EXTERNAL_JOBS_CONFIG', '')
        if not path:
            return
        try:
            data = json.loads(Path(path).read_text(encoding='utf-8'))
            if not isinstance(data, dict) or data.get('schema_version') != 1 or not isinstance(data.get('jobs'), list):
                raise ValueError('expected schema_version=1 and jobs list')
            if any(not isinstance(job, dict) or not isinstance(job.get('id'), str) or not job['id']
                   for job in data['jobs']):
                raise ValueError('external jobs need nonempty string ids')
            identifiers = [job['id'] for job in data['jobs']]
            if len(set(identifiers)) != len(identifiers):
                raise ValueError('duplicate external job id')
        except (OSError, ValueError, KeyError, TypeError) as exc:
            log(f'ERROR external jobs config: {exc}')
            return  # Never disrupt the existing Daily chain.
        for job in data['jobs']:
            if job.get('enabled') is not True:
                continue
            key = job['id']
            previous = self.children.get(key)
            if previous is not None:
                code = previous.poll()
                if code is None:
                    continue
                if code:
                    log(f'ERROR external trigger {key} exit={code}')
            try:
                argv = job['argv']
                cwd = Path(job['cwd'])
                if (not isinstance(argv, list) or not argv or
                        any(not isinstance(v, str) or not v for v in argv)
                        or not Path(argv[0]).is_absolute() or not cwd.is_absolute()):
                    raise ValueError('absolute executable/cwd and argv list required')
                if dry_run:
                    log(f'[dry-run] external trigger {key}: {argv}')
                    continue
                # The hook is a short-lived controller. Its own durable trigger
                # lock handles Scheduler restart and overlapping invocations.
                self.children[key] = subprocess.Popen(argv, cwd=cwd,
                    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL, start_new_session=True)
            except (OSError, ValueError, KeyError, TypeError) as exc:
                log(f'ERROR external trigger {key}: {exc}')


def main():
    parser = argparse.ArgumentParser(description='External Daily hook configuration (opt-in only)')
    parser.add_argument('--config', required=True)
    args = parser.parse_args()
    ExternalDailyJobs().tick(print, config_path=args.config, dry_run=True)


if __name__ == '__main__':
    main()
