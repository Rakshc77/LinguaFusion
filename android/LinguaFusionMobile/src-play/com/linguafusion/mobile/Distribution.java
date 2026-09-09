package com.linguafusion.mobile;

/**
 * How this build reached the phone, which decides what it may do about
 * updates. Play keeps this build current, and its Device and Network Abuse
 * policy forbids an app distributed there from replacing itself by any other
 * route -- so the self-updater is compiled out rather than merely hidden, and
 * REQUEST_INSTALL_PACKAGES is removed from this flavour's manifest.
 *
 * The hosted interface still updates itself. That is interpreted code in a
 * WebView, which the same policy explicitly excludes.
 */
final class Distribution {
    static final boolean SELF_UPDATE = false;
    static final String CHANNEL = "play";

    private Distribution() {
    }
}
