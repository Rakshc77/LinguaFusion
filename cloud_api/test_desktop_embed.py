"""Contract for the secure account surface embedded by the Windows app."""

from pathlib import Path


WEB = Path(__file__).with_name("web")


def test_desktop_embed_keeps_auth_and_owner_logic_in_the_cloud_surface():
    script = (WEB / "pilot.mjs").read_text(encoding="utf-8")
    styles = (WEB / "pilot.css").read_text(encoding="utf-8")

    assert "shellParams.get('embed') === 'desktop'" in script
    assert "account:'viewAccount', say:'viewSay'" in script
    assert "if (embeddedView) showView(embeddedView)" in script
    assert 'html[data-embed="desktop"] .bottom-nav { display:none; }' in styles
    assert 'html[data-embed="desktop"] #viewAccount' in styles
    assert 'html[data-embed="desktop"] #viewSay' in styles


def test_desktop_points_only_to_fixed_embedded_feature_routes():
    desktop = (Path(__file__).parents[1] / "desktop" / "main.py").read_text(encoding="utf-8")
    assert '"https://linguafusion-cloud-pilot-jl77ipbeua-ey.a.run.app"' in desktop
    assert '/pilot/?embed=desktop&view={safe_view}' in desktop
    assert 'view if view in {"account", "say"} else "account"' in desktop
    assert 'QDesktopServices.openUrl(self._online_account_url())' in desktop
