#!/usr/bin/env python3
"""
ShowWise Backend - API Keys Management CLI

Simple CLI to list, generate, revoke, and delete API keys stored in `data/api_keys.json`.
"""

import os
import sys
import json
import argparse
from datetime import datetime
import secrets

DATA_DIR = 'data'
API_KEYS_FILE = os.path.join(DATA_DIR, 'api_keys.json')
ORGS_FILE = os.path.join(DATA_DIR, 'organizations.json')


def load_json(path, default=None):
    try:
        with open(path, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return default if default is not None else {}
    except Exception as e:
        print(f"Error loading {path}: {e}")
        sys.exit(1)


def save_json(path, data):
    try:
        with open(path, 'w') as f:
            json.dump(data, f, indent=2)
        return True
    except Exception as e:
        print(f"Error saving {path}: {e}")
        return False


def list_keys():
    keys = load_json(API_KEYS_FILE, {})
    if not keys:
        print('No API keys found.')
        return

    print('\n' + '='*70)
    print('  ShowWise API Keys')
    print('='*70)
    print(f"\n{'Key':<48} {'Name':<20} {'Active':<6}")
    print('-'*70)
    for k, meta in keys.items():
        key_short = k[:44] + '...' if len(k) > 47 else k
        name = meta.get('name', '')
        active = 'yes' if meta.get('active', False) else 'no'
        print(f"{key_short:<48} {name:<20} {active:<6}")
    print('-'*70)
    print(f"Total keys: {len(keys)}\n")


def generate_key(org_slug, name='home-key'):
    orgs = load_json(ORGS_FILE, {})
    if org_slug not in orgs:
        print(f"Error: organization '{org_slug}' not found in {ORGS_FILE}.")
        return 1

    keys = load_json(API_KEYS_FILE, {})
    api_key = 'sk_' + secrets.token_urlsafe(32)
    keys[api_key] = {
        'name': name,
        'org_slug': org_slug,
        'created_at': datetime.now().isoformat(),
        'created_by': 'cli',
        'last_used': None,
        'active': True
    }

    if save_json(API_KEYS_FILE, keys):
        print('\n✓ API key created successfully:')
        print(api_key + '\n')
        return 0
    else:
        print('\n✗ Failed to save API key.')
        return 1


def revoke_key(key):
    keys = load_json(API_KEYS_FILE, {})
    if key not in keys:
        print('Error: API key not found.')
        return 1

    keys[key]['active'] = False
    keys[key]['revoked_at'] = datetime.now().isoformat()
    keys[key]['revoked_by'] = 'cli'

    if save_json(API_KEYS_FILE, keys):
        print('✓ API key revoked.')
        return 0
    else:
        print('✗ Failed to revoke API key.')
        return 1


def delete_key(key):
    keys = load_json(API_KEYS_FILE, {})
    if key not in keys:
        print('Error: API key not found.')
        return 1

    confirm = input(f"Are you sure you want to delete the key {key[:20] + '...'}? (yes/no): ")
    if confirm.lower() != 'yes':
        print('Deletion cancelled.')
        return 1

    del keys[key]
    if save_json(API_KEYS_FILE, keys):
        print('✓ API key deleted.')
        return 0
    else:
        print('✗ Failed to delete API key.')
        return 1


def main():
    parser = argparse.ArgumentParser(description='Manage ShowWise API keys')
    sub = parser.add_subparsers(dest='command')

    sub.add_parser('list', help='List all API keys')

    g = sub.add_parser('generate', help='Generate a new API key for an organization')
    g.add_argument('org', help='Organization slug')
    g.add_argument('--name', '-n', default='home-key', help='Name/label for the key')

    r = sub.add_parser('revoke', help='Revoke (disable) an API key')
    r.add_argument('key', help='Full API key to revoke')

    d = sub.add_parser('delete', help='Delete an API key permanently')
    d.add_argument('key', help='Full API key to delete')

    args = parser.parse_args()

    if not os.path.exists(DATA_DIR):
        print(f"Error: Data directory '{DATA_DIR}' not found.")
        sys.exit(1)

    if args.command == 'list':
        list_keys()

    elif args.command == 'generate':
        sys.exit(generate_key(args.org, args.name))

    elif args.command == 'revoke':
        sys.exit(revoke_key(args.key))

    elif args.command == 'delete':
        sys.exit(delete_key(args.key))

    else:
        parser.print_help()


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('\nOperation cancelled by user.')
        sys.exit(0)
