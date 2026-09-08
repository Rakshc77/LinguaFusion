"""Build/promote the EXISTING pilot, preserving identity, secrets and limits.

Uses Application Default Credentials (never a service-account key in git).
Default is read-only. --build uploads an explicit, credential-free allowlist;
--promote BUILD_ID changes only the existing service's container image.
Builds and hosting can cost money; this does not alter any budget or IAM grant.
"""
import argparse
import io
import json
import pathlib
import tarfile
import uuid

import google.auth
from google.auth.transport.requests import AuthorizedSession

ROOT = pathlib.Path(__file__).resolve().parents[1]
PROJECT = 'linguafusion-f24fe'
SERVICE = f'projects/{PROJECT}/locations/europe-west3/services/linguafusion-cloud-pilot'
IMAGE = f'europe-west3-docker.pkg.dev/{PROJECT}/linguafusion/cloud-pilot'
BUCKET = f'{PROJECT}_cloudbuild'


def checked(response):
    if not response.ok:
        raise SystemExit(f'Google API returned HTTP {response.status_code}; no response body printed.')
    return response.json()


def source_archive():
    buffer = io.BytesIO()
    files = []
    # This ignore file is an exact allowlist, not a recursive directory upload.
    for line in (ROOT / 'cloud_api/Dockerfile.dockerignore').read_text().splitlines():
        if line.startswith('!') and not line.endswith('/'):
            name = line[1:]
            path = (ROOT / name).resolve()
            if not path.is_relative_to(ROOT) or not path.is_file():
                raise SystemExit(f'Missing or unsafe build input: {name}')
            if any(part in {'.git', '.claude', 'local-data', 'storage'} for part in path.parts):
                raise SystemExit('Private directory in build allowlist.')
            files.append((name, path))
    with tarfile.open(fileobj=buffer, mode='w:gz') as archive:
        for name, path in files:
            archive.add(path, arcname=name, recursive=False)
    return buffer.getvalue(), len(files)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument('--build', action='store_true')
    actions.add_argument('--status', metavar='BUILD_ID')
    actions.add_argument('--promote', metavar='BUILD_ID')
    args = parser.parse_args()
    credentials, _ = google.auth.default(scopes=['https://www.googleapis.com/auth/cloud-platform'])
    session = AuthorizedSession(credentials.with_quota_project(PROJECT))
    service_url = f'https://run.googleapis.com/v2/{SERVICE}'
    if args.build:
        payload, count = source_archive()
        tag = uuid.uuid4().hex
        object_name = f'source/codex-{tag}.tar.gz'
        checked(session.post(f'https://storage.googleapis.com/upload/storage/v1/b/{BUCKET}/o',
            params={'uploadType': 'media', 'name': object_name, 'ifGenerationMatch': '0'},
            data=payload, headers={'Content-Type': 'application/gzip'}, timeout=60))
        operation = checked(session.post(f'https://cloudbuild.googleapis.com/v1/projects/{PROJECT}/builds',
            json={'source': {'storageSource': {'bucket': BUCKET, 'object': object_name}},
                  'steps': [{'name': 'gcr.io/cloud-builders/docker',
                             'args': ['build', '-f', 'cloud_api/Dockerfile', '-t', f'{IMAGE}:{tag}', '.']}],
                  'images': [f'{IMAGE}:{tag}'], 'timeout': '1200s'}, timeout=40))
        print(json.dumps({'build_id': operation.get('metadata', {}).get('build', {}).get('id'),
                          'operation': operation.get('name'), 'source_files': count, 'source_bytes': len(payload)}))
    elif args.status or args.promote:
        build_id = args.status or args.promote
        if not all(c in '0123456789abcdef-' for c in build_id):
            raise SystemExit('Invalid build ID')
        build = checked(session.get(f'https://cloudbuild.googleapis.com/v1/projects/{PROJECT}/builds/{build_id}', timeout=25))
        print(json.dumps({'build_id': build_id, 'status': build['status']}))
        if args.promote:
            if build['status'] != 'SUCCESS':
                raise SystemExit('Only a successful build can be promoted.')
            images = build.get('results', {}).get('images', [])
            if len(images) != 1 or not images[0]['name'].startswith(IMAGE + ':'):
                raise SystemExit('Build is not a LinguaFusion pilot image.')
            service = checked(session.get(service_url, timeout=25))
            containers = service['template']['containers']
            if len(containers) != 1:
                raise SystemExit('Unexpected service layout; manual review required.')
            previous = containers[0]['image']
            containers[0]['image'] = f"{IMAGE}@{images[0]['digest']}"
            operation = checked(session.patch(service_url, params={'updateMask': 'template.containers'},
                json={'name': SERVICE, 'etag': service['etag'], 'template': {'containers': containers}}, timeout=40))
            print(json.dumps({'operation': operation['name'], 'previous_image': previous,
                              'new_image': containers[0]['image']}))
    else:
        service = checked(session.get(service_url, timeout=25))
        print(json.dumps({'ready_revision': service.get('latestReadyRevision'),
            'created_revision': service.get('latestCreatedRevision'), 'uri': service.get('uri'),
            'image': service['template']['containers'][0]['image'], 'reconciling': service.get('reconciling', False)}))


if __name__ == '__main__':
    main()
