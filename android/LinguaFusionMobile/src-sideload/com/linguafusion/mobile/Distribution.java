package com.linguafusion.mobile;

/**
 * How this build reached the phone, which decides what it may do about
 * updates. The sideload build is downloaded from the owner's own service, so
 * nothing else will ever update it and it has to update itself.
 */
final class Distribution {
    /** Google Play forbids an app it distributes from updating itself. This
     *  build does not come from Play, so it must. */
    static final boolean SELF_UPDATE = true;
    static final String CHANNEL = "sideload";

    private Distribution() {
    }
}
