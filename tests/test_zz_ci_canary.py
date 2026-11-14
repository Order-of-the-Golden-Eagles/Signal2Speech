"""Deliberate failure for #38: proves CI goes red. Removed in the next commit; never merge."""


def test_deliberate_failure_for_issue_38():
    assert False, "deliberate #38 failure: CI must report this"
