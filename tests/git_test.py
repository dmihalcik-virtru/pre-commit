# -*- coding: utf-8 -*-
from __future__ import absolute_import
from __future__ import unicode_literals

import os.path

import pytest

from pre_commit import git
from pre_commit.errors import FatalError
from pre_commit.util import cmd_output
from pre_commit.util import cwd
from testing.fixtures import git_dir
from testing.util import xfailif_no_symlink


def test_get_root_at_root(tempdir_factory):
    path = git_dir(tempdir_factory)
    with cwd(path):
        assert os.path.normcase(git.get_root()) == os.path.normcase(path)


def test_get_root_deeper(tempdir_factory):
    path = git_dir(tempdir_factory)

    foo_path = os.path.join(path, 'foo')
    os.mkdir(foo_path)
    with cwd(foo_path):
        assert os.path.normcase(git.get_root()) == os.path.normcase(path)


def test_get_root_not_git_dir(tempdir_factory):
    with cwd(tempdir_factory.get()):
        with pytest.raises(FatalError):
            git.get_root()


def test_get_staged_files_deleted(tempdir_factory):
    path = git_dir(tempdir_factory)
    with cwd(path):
        open('test', 'a').close()
        cmd_output('git', 'add', 'test')
        cmd_output('git', 'commit', '-m', 'foo', '--allow-empty')
        cmd_output('git', 'rm', '--cached', 'test')
        assert git.get_staged_files() == []


def test_is_not_in_merge_conflict(tempdir_factory):
    path = git_dir(tempdir_factory)
    with cwd(path):
        assert git.is_in_merge_conflict() is False


def test_is_in_merge_conflict(in_merge_conflict):
    assert git.is_in_merge_conflict() is True


def test_is_in_merge_conflict_submodule(in_conflicting_submodule):
    assert git.is_in_merge_conflict() is True


def test_cherry_pick_conflict(in_merge_conflict):
    cmd_output('git', 'merge', '--abort')
    foo_ref = cmd_output('git', 'rev-parse', 'foo')[1].strip()
    cmd_output('git', 'cherry-pick', foo_ref, retcode=None)
    assert git.is_in_merge_conflict() is False


@pytest.fixture
def get_files_matching_func():
    def get_filenames():
        return (
            '.pre-commit-hooks.yaml',
            'pre_commit/main.py',
            'pre_commit/git.py',
            'im_a_file_that_doesnt_exist.py',
        )

    return git.get_files_matching(get_filenames)


def test_get_files_matching_base(get_files_matching_func):
    ret = get_files_matching_func('', '^$')
    assert ret == {
        '.pre-commit-hooks.yaml',
        'pre_commit/main.py',
        'pre_commit/git.py',
    }


@xfailif_no_symlink
def test_matches_broken_symlink(tmpdir):  # pragma: no cover (non-windwos)
    with tmpdir.as_cwd():
        os.symlink('does-not-exist', 'link')
        func = git.get_files_matching(lambda: ('link',))
        assert func('', '^$') == {'link'}


def test_get_files_matching_total_match(get_files_matching_func):
    ret = get_files_matching_func('^.*\\.py$', '^$')
    assert ret == {'pre_commit/main.py', 'pre_commit/git.py'}


def test_does_search_instead_of_match(get_files_matching_func):
    ret = get_files_matching_func('\\.yaml$', '^$')
    assert ret == {'.pre-commit-hooks.yaml'}


def test_does_not_include_deleted_fileS(get_files_matching_func):
    ret = get_files_matching_func('exist.py', '^$')
    assert ret == set()


def test_exclude_removes_files(get_files_matching_func):
    ret = get_files_matching_func('', '\\.py$')
    assert ret == {'.pre-commit-hooks.yaml'}


def resolve_conflict():
    with open('conflict_file', 'w') as conflicted_file:
        conflicted_file.write('herp\nderp\n')
    cmd_output('git', 'add', 'conflict_file')


def test_get_conflicted_files(in_merge_conflict):
    resolve_conflict()
    with open('other_file', 'w') as other_file:
        other_file.write('oh hai')
    cmd_output('git', 'add', 'other_file')

    ret = set(git.get_conflicted_files())
    assert ret == {'conflict_file', 'other_file'}


def test_get_conflicted_files_in_submodule(in_conflicting_submodule):
    resolve_conflict()
    assert set(git.get_conflicted_files()) == {'conflict_file'}


def test_get_conflicted_files_unstaged_files(in_merge_conflict):
    """This case no longer occurs, but it is a useful test nonetheless"""
    resolve_conflict()

    # Make unstaged file.
    with open('bar_only_file', 'w') as bar_only_file:
        bar_only_file.write('new contents!\n')

    ret = set(git.get_conflicted_files())
    assert ret == {'conflict_file'}


MERGE_MSG = b"Merge branch 'foo' into bar\n\nConflicts:\n\tconflict_file\n"
OTHER_MERGE_MSG = MERGE_MSG + b'\tother_conflict_file\n'


@pytest.mark.parametrize(
    ('input', 'expected_output'),
    (
        (MERGE_MSG, ['conflict_file']),
        (OTHER_MERGE_MSG, ['conflict_file', 'other_conflict_file']),
    ),
)
def test_parse_merge_msg_for_conflicts(input, expected_output):
    ret = git.parse_merge_msg_for_conflicts(input)
    assert ret == expected_output


def test_get_changed_files():
    files = git.get_changed_files(
        '78c682a1d13ba20e7cb735313b9314a74365cd3a',
        '3387edbb1288a580b37fe25225aa0b856b18ad1a',
    )
    assert files == ['CHANGELOG.md', 'setup.py']

    # files changed in source but not in origin should not be returned
    files = git.get_changed_files('HEAD~10', 'HEAD')
    assert files == []


@pytest.mark.parametrize(
    ('s', 'expected'),
    (
        ('foo\0bar\0', ['foo', 'bar']),
        ('foo\0', ['foo']),
        ('', []),
        ('foo', ['foo']),
    ),
)
def test_zsplit(s, expected):
    assert git.zsplit(s) == expected


@pytest.fixture
def non_ascii_repo(tmpdir):
    repo = tmpdir.join('repo').ensure_dir()
    with repo.as_cwd():
        cmd_output('git', 'init', '.')
        cmd_output('git', 'commit', '--allow-empty', '-m', 'initial commit')
        repo.join('интервью').ensure()
        cmd_output('git', 'add', '.')
        cmd_output('git', 'commit', '--allow-empty', '-m', 'initial commit')
        yield repo


def test_all_files_non_ascii(non_ascii_repo):
    ret = git.get_all_files()
    assert ret == ['интервью']


def test_staged_files_non_ascii(non_ascii_repo):
    non_ascii_repo.join('интервью').write('hi')
    cmd_output('git', 'add', '.')
    assert git.get_staged_files() == ['интервью']


def test_changed_files_non_ascii(non_ascii_repo):
    ret = git.get_changed_files('HEAD', 'HEAD^')
    assert ret == ['интервью']


def test_get_conflicted_files_non_ascii(in_merge_conflict):
    open('интервью', 'a').close()
    cmd_output('git', 'add', '.')
    ret = git.get_conflicted_files()
    assert ret == {'conflict_file', 'интервью'}
