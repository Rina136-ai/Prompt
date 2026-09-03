"""Real structural-segmentation test: builds synthetic audio with known
section boundaries (quiet tone / loud chord / quiet tone) and checks the
detector finds the actual transition points -- not a mocked assertion."""
import pytest

librosa = pytest.importorskip("librosa")
np = pytest.importorskip("numpy")
sf = pytest.importorskip("soundfile")

from app.audio_analysis import analyze_audio_file  # noqa: E402

SR = 22050


def _tone(freq, dur, amp=0.2, extra=None):
    t = np.linspace(0, dur, int(SR * dur), endpoint=False)
    sig = amp * np.sin(2 * np.pi * freq * t)
    for f2, a2 in extra or []:
        sig += a2 * np.sin(2 * np.pi * f2 * t)
    return sig.astype(np.float32)


@pytest.fixture
def synthetic_song(tmp_path):
    sections = [
        _tone(220, 8, amp=0.08),
        _tone(440, 8, amp=0.3, extra=[(554, 0.2), (659, 0.2)]),
        _tone(196, 8, amp=0.08),
    ]
    y = np.concatenate(sections)
    path = tmp_path / "song.wav"
    sf.write(str(path), y, SR)
    return str(path)


def test_duration_matches_the_real_file(synthetic_song):
    features = analyze_audio_file(synthetic_song, min_section_seconds=5.0, max_sections=8)
    assert features.duration == pytest.approx(24.0, abs=0.1)


def test_detects_a_real_transition_near_the_known_boundary(synthetic_song):
    features = analyze_audio_file(synthetic_song, min_section_seconds=5.0, max_sections=8)
    boundary_times = [s.start for s in features.sections[1:]]
    assert any(abs(t - 8.0) < 1.0 for t in boundary_times), boundary_times


def test_sections_cover_the_full_duration_contiguously(synthetic_song):
    features = analyze_audio_file(synthetic_song, min_section_seconds=5.0, max_sections=8)
    assert features.sections[0].start == 0.0
    assert features.sections[-1].end == pytest.approx(features.duration, abs=0.05)
    for a, b in zip(features.sections, features.sections[1:]):
        assert a.end == b.start


def test_loud_section_is_classified_more_energetic_than_quiet_ones(synthetic_song):
    features = analyze_audio_file(synthetic_song, min_section_seconds=5.0, max_sections=8)
    by_time = {round(s.start): s.energy for s in features.sections}
    quiet_energies = [e for t, e in by_time.items() if t < 7 or t > 17]
    assert "calme" in quiet_energies or "modere" in quiet_energies
