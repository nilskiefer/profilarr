# git/operations/resolve.py

import yaml
from git import GitCommandError
import logging
from typing import Dict, Any
import os
from copy import deepcopy

logger = logging.getLogger(__name__)


def get_version_data(repo, ref, file_path):
    """Get YAML data from a specific version of a file."""
    try:
        content = repo.git.show(f'{ref}:{file_path}')
        return yaml.safe_load(content) if content else None
    except GitCommandError:
        return None


def resolve_conflicts(
        repo, resolutions: Dict[str, Dict[str, str]]) -> Dict[str, Any]:
    logger.debug(f"Received resolutions for files: {list(resolutions.keys())}")
    """
    Resolve merge conflicts based on provided resolutions.
    """
    try:
        status = repo.git.status('--porcelain', '-z').split('\0')
        conflicts = []
        for item in status:
            if not item or len(item) < 4:
                continue
            x, y, file_path = item[0], item[1], item[3:]
            # Include modify/delete conflicts
            if 'U' in (x, y) or (x == 'D' and y == 'D') or (
                    x == 'D' and y == 'U') or (x == 'U' and y == 'D'):
                conflicts.append((file_path, x, y))

        # Track which files are modify/delete conflicts
        modify_delete_conflicts = {
            path: (x == 'D' and y == 'U') or (x == 'U' and y == 'D')
            for path, x, y in conflicts
        }

        # Validate resolutions are for actual conflicting files
        for file_path in resolutions:
            if file_path not in {path for path, _, _ in conflicts}:
                return {
                    'success': False,
                    'error': f"File not in conflict: {file_path}"
                }

        # Store initial states for rollback
        initial_states = {}
        for file_path in resolutions:
            try:
                full_path = os.path.join(repo.working_dir, file_path)
                try:
                    with open(full_path, 'r') as f:
                        initial_states[file_path] = f.read()
                except FileNotFoundError:
                    initial_states[file_path] = None
            except Exception as e:
                return {
                    'success': False,
                    'error': f"Couldn't read file {file_path}: {str(e)}"
                }

        results = {}
        for file_path, field_resolutions in resolutions.items():
            # Handle modify/delete conflicts differently
            if modify_delete_conflicts[file_path]:
                logger.debug(
                    f"Handling modify/delete conflict for {file_path}")

                # Get the existing version (either from HEAD or MERGE_HEAD)
                head_data = get_version_data(repo, 'HEAD', file_path)
                merge_head_data = get_version_data(repo, 'MERGE_HEAD',
                                                   file_path)

                # Determine which version exists
                is_deleted_in_head = head_data is None
                existing_data = merge_head_data if is_deleted_in_head else head_data
                logger.debug(f"Existing version data: {existing_data}")

                choice = field_resolutions.get('file')
                if not choice:
                    raise Exception(
                        "No resolution provided for modify/delete conflict")

                full_path = os.path.join(repo.working_dir, file_path)

                if choice == 'local':
                    if is_deleted_in_head:
                        logger.debug(f"Keeping file deleted: {file_path}")
                        # File should stay deleted
                        try:
                            os.remove(full_path)
                        except FileNotFoundError:
                            pass  # File is already gone
                        repo.index.remove([file_path])
                    else:
                        logger.debug(f"Keeping local version: {file_path}")
                        # Keep our version
                        with open(full_path, 'w') as f:
                            yaml.safe_dump(head_data,
                                           f,
                                           default_flow_style=False)
                        repo.index.add([file_path])

                elif choice == 'incoming':
                    if is_deleted_in_head:
                        logger.debug(
                            f"Restoring from incoming version: {file_path}")
                        # Restore the file from MERGE_HEAD
                        with open(full_path, 'w') as f:
                            yaml.safe_dump(merge_head_data,
                                           f,
                                           default_flow_style=False)
                        repo.index.add([file_path])
                    else:
                        logger.debug(f"Accepting deletion: {file_path}")
                        # Accept the deletion
                        try:
                            os.remove(full_path)
                        except FileNotFoundError:
                            pass  # File is already gone
                        repo.index.remove([file_path])

                results[file_path] = {
                    'resolution':
                    choice,
                    'action':
                    'delete' if (choice == 'local' and is_deleted_in_head) or
                    (choice == 'incoming' and not is_deleted_in_head) else
                    'keep'
                }

            else:
                # Regular conflict resolution
                # Get all three versions
                base_data = get_version_data(repo, 'HEAD^', file_path)
                ours_data = get_version_data(repo, 'HEAD', file_path)
                theirs_data = get_version_data(repo, 'MERGE_HEAD', file_path)

                if not base_data or not ours_data or not theirs_data:
                    raise Exception(
                        f"Couldn't get all versions of {file_path}")

                # Start with a deep copy of ours_data to preserve all fields
                resolved_data = deepcopy(ours_data)

                # Track changes
                kept_values = {}
                discarded_values = {}

                # Handle each resolution field
                for field, choice in field_resolutions.items():
                    if field.startswith('custom_format_'):
                        try:
                            cf_id = int(field.split('_')[-1])
                        except ValueError:
                            raise Exception(
                                f"Invalid custom_format ID in field: {field}")

                        ours_cf = next(
                            (item
                             for item in ours_data.get('custom_formats', [])
                             if item['id'] == cf_id), None)
                        theirs_cf = next(
                            (item
                             for item in theirs_data.get('custom_formats', [])
                             if item['id'] == cf_id), None)

                        if choice == 'local' and ours_cf:
                            resolved_cf = ours_cf
                            kept_values[field] = ours_cf
                            discarded_values[field] = theirs_cf
                        elif choice == 'incoming' and theirs_cf:
                            resolved_cf = theirs_cf
                            kept_values[field] = theirs_cf
                            discarded_values[field] = ours_cf
                        else:
                            raise Exception(
                                f"Invalid choice or missing custom_format ID {cf_id}"
                            )

                        resolved_cf_list = resolved_data.get(
                            'custom_formats', [])
                        for idx, item in enumerate(resolved_cf_list):
                            if item['id'] == cf_id:
                                resolved_cf_list[idx] = resolved_cf
                                break
                        else:
                            resolved_cf_list.append(resolved_cf)
                        resolved_data['custom_formats'] = resolved_cf_list

                    elif field.startswith('tag_'):
                        tag_name = field[len('tag_'):]
                        current_tags = set(resolved_data.get('tags', []))

                        if choice == 'local':
                            if tag_name in ours_data.get('tags', []):
                                current_tags.add(tag_name)
                                kept_values[field] = 'local'
                                discarded_values[field] = 'incoming'
                            else:
                                current_tags.discard(tag_name)
                                kept_values[field] = 'none'
                                discarded_values[field] = 'incoming'
                        elif choice == 'incoming':
                            if tag_name in theirs_data.get('tags', []):
                                current_tags.add(tag_name)
                                kept_values[field] = 'incoming'
                                discarded_values[field] = 'local'
                            else:
                                current_tags.discard(tag_name)
                                kept_values[field] = 'none'
                                discarded_values[field] = 'local'
                        else:
                            raise Exception(
                                f"Invalid choice for tag field: {field}")

                        resolved_data['tags'] = sorted(current_tags)

                    else:
                        field_key = field
                        if choice == 'local':
                            resolved_data[field_key] = ours_data.get(field_key)
                            kept_values[field_key] = ours_data.get(field_key)
                            discarded_values[field_key] = theirs_data.get(
                                field_key)
                        elif choice == 'incoming':
                            resolved_data[field_key] = theirs_data.get(
                                field_key)
                            kept_values[field_key] = theirs_data.get(field_key)
                            discarded_values[field_key] = ours_data.get(
                                field_key)
                        else:
                            raise Exception(
                                f"Invalid choice for field: {field}")

                # Write resolved version
                full_path = os.path.join(repo.working_dir, file_path)
                with open(full_path, 'w') as f:
                    yaml.safe_dump(resolved_data, f, default_flow_style=False)

                # Stage the resolved file
                repo.index.add([file_path])

                results[file_path] = {
                    'kept_values': kept_values,
                    'discarded_values': discarded_values
                }

                logger.debug(
                    f"Successfully resolved regular conflict for {file_path}")

        logger.debug("==== Status after resolve_conflicts ====")
        status_output = repo.git.status('--porcelain', '-z').split('\0')
        for item in status_output:
            if item:
                logger.debug(f"File status: {item}")
        logger.debug("=======================================")

        return {'success': True, 'results': results}

    except Exception as e:
        # Rollback on any error
        for file_path, initial_state in initial_states.items():
            try:
                full_path = os.path.join(repo.working_dir, file_path)
                if initial_state is None:
                    try:
                        os.remove(full_path)
                    except FileNotFoundError:
                        pass
                else:
                    with open(full_path, 'w') as f:
                        f.write(initial_state)
            except Exception as rollback_error:
                logger.error(
                    f"Failed to rollback {file_path}: {str(rollback_error)}")

        logger.error(f"Failed to resolve conflicts: {str(e)}")
        return {'success': False, 'error': str(e)}
