"""
Tests for escalation logic and configuration.
"""

import pytest
from src.config import get_escalation_stage, ESCALATION_MATRIX


class TestEscalationStage:
    """Tests for get_escalation_stage() which uses both days_overdue and follow_up_count."""

    # ── Not overdue ──────────────────────────────────────────
    def test_not_overdue_returns_zero(self):
        assert get_escalation_stage(0, 0) == 0

    def test_negative_days_returns_zero(self):
        assert get_escalation_stage(-5, 0) == 0

    # ── Stage from days_overdue alone (follow_up_count=0) ────
    def test_stage1_day_1(self):
        assert get_escalation_stage(1, 0) == 1

    def test_stage1_day_7(self):
        assert get_escalation_stage(7, 0) == 1

    def test_stage2_day_8(self):
        assert get_escalation_stage(8, 0) == 2

    def test_stage2_day_14(self):
        assert get_escalation_stage(14, 0) == 2

    def test_stage3_day_15(self):
        assert get_escalation_stage(15, 0) == 3

    def test_stage3_day_21(self):
        assert get_escalation_stage(21, 0) == 3

    def test_stage4_day_22(self):
        assert get_escalation_stage(22, 0) == 4

    def test_stage4_day_30(self):
        assert get_escalation_stage(30, 0) == 4

    def test_stage5_day_31(self):
        assert get_escalation_stage(31, 0) == 5

    def test_stage5_day_100(self):
        assert get_escalation_stage(100, 0) == 5

    # ── follow_up_count elevates stage (tone never regresses) ─
    def test_followup_elevates_stage(self):
        """3 days overdue (stage 1) but 2 prior follow-ups → stage 3."""
        assert get_escalation_stage(3, 2) == 3

    def test_followup_does_not_lower_stage(self):
        """21 days overdue (stage 3) with 0 follow-ups → still stage 3."""
        assert get_escalation_stage(21, 0) == 3

    def test_high_followup_caps_at_5(self):
        """follow_up_count=10 → followup_stage = min(11,5) = 5."""
        assert get_escalation_stage(1, 10) == 5

    def test_followup_3_with_day_1(self):
        """1 day overdue but 3 prior follow-ups → stage 4."""
        assert get_escalation_stage(1, 3) == 4

    def test_both_signals_agree(self):
        """14 days overdue (stage 2) + 1 follow-up (stage 2) → stage 2."""
        assert get_escalation_stage(14, 1) == 2

    def test_days_higher_than_followup(self):
        """25 days overdue (stage 4) + 0 follow-ups → stage 4."""
        assert get_escalation_stage(25, 0) == 4


class TestEscalationMatrix:
    """Validate the escalation matrix configuration."""

    def test_matrix_has_5_stages(self):
        assert len(ESCALATION_MATRIX) == 5

    def test_all_stages_have_required_keys(self):
        required = {"stage_name", "trigger_days", "tone", "key_message", "cta"}
        for stage, config in ESCALATION_MATRIX.items():
            assert required.issubset(config.keys()), f"Stage {stage} missing keys"

    def test_stages_cover_continuous_range(self):
        """Day ranges should be contiguous: 1-7, 8-14, 15-21, 22-30, 31+."""
        prev_high = 0
        for stage in sorted(ESCALATION_MATRIX.keys()):
            low, high = ESCALATION_MATRIX[stage]["trigger_days"]
            assert low == prev_high + 1, f"Stage {stage}: gap at day {prev_high+1}"
            prev_high = high
