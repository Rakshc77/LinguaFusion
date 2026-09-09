package com.linguafusion.mobile;

import android.content.Context;
import android.graphics.Rect;
import android.net.Uri;

import com.google.android.gms.tasks.Tasks;
import com.google.mlkit.vision.common.InputImage;
import com.google.mlkit.vision.text.Text;
import com.google.mlkit.vision.text.TextRecognition;
import com.google.mlkit.vision.text.TextRecognizer;
import com.google.mlkit.vision.text.latin.TextRecognizerOptions;

import java.io.IOException;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.List;
import java.util.concurrent.TimeUnit;

/**
 * Reading text out of a picture, on the device.
 *
 * The Latin model arrives once through Play Services and then works with no
 * network, the same way the translation packs and the speech model do.
 * Recognition itself always runs on the device. It covers English, German,
 * Spanish and French.
 * **Arabic is not one of ML Kit's scripts** -- the others are Chinese,
 * Devanagari, Japanese and Korean -- so Arabic pictures still need the cloud,
 * and the caller says so rather than returning a confident mess of Latin
 * letters that were never there.
 *
 * Blocking. Not for the UI thread.
 */
final class OfflineVision {
    /** Long enough for a large photo on a slow phone. */
    private static final long TIMEOUT_SECONDS = 60;

    private final Context context;
    private TextRecognizer recognizer;

    OfflineVision(Context context) {
        this.context = context.getApplicationContext();
    }

    /** The scripts the bundled model can read, for anything asking. */
    static boolean canRead(String languageCode) {
        // Latin script only. Arabic is the one offered language it cannot do.
        return OfflineLanguages.isSupported(languageCode)
                && !"ar".equals(OfflineLanguages.normalise(languageCode));
    }

    /**
     * Reads a picture.
     *
     * @return the text laid out roughly as it appeared, or a message
     *         beginning with "ERROR: "
     */
    synchronized String read(Uri picture) {
        if (picture == null) {
            return "ERROR: No picture was chosen.";
        }
        try {
            final InputImage image = InputImage.fromFilePath(context, picture);
            if (recognizer == null) {
                recognizer = TextRecognition.getClient(TextRecognizerOptions.DEFAULT_OPTIONS);
            }
            final Text result = Tasks.await(recognizer.process(image),
                    TIMEOUT_SECONDS, TimeUnit.SECONDS);
            final String text = layout(result);
            if (text.isEmpty()) {
                return "ERROR: No readable text was found. Arabic cannot be read "
                        + "offline; use the cloud for that.";
            }
            return text;
        } catch (IOException unreadable) {
            return "ERROR: That picture could not be opened.";
        } catch (Exception failure) {
            return "ERROR: The picture could not be read (" + failure.getClass().getSimpleName() + ").";
        }
    }

    /**
     * Rebuilds something close to the page's own layout.
     *
     * ML Kit returns blocks of lines with their positions but no notion of
     * reading order across a page, so blocks are sorted top to bottom and a
     * blank line separates them. Lines within a block keep their own order.
     * This is deliberately simpler than the cloud's reconstruction, which
     * rebuilds columns and tables from the geometry; a phone gets paragraphs,
     * not spreadsheets, and it is honest about that rather than inventing
     * structure it did not detect.
     */
    private static String layout(Text result) {
        final List<Text.TextBlock> blocks = new ArrayList<>(result.getTextBlocks());
        Collections.sort(blocks, new Comparator<Text.TextBlock>() {
            @Override public int compare(Text.TextBlock first, Text.TextBlock second) {
                final Rect one = first.getBoundingBox();
                final Rect two = second.getBoundingBox();
                if (one == null || two == null) {
                    return 0;
                }
                // Top to bottom, then left to right for anything side by side.
                final int vertical = Integer.compare(one.top, two.top);
                return vertical != 0 ? vertical : Integer.compare(one.left, two.left);
            }
        });

        final StringBuilder page = new StringBuilder();
        for (Text.TextBlock block : blocks) {
            if (page.length() > 0) {
                page.append('\n').append('\n');
            }
            for (int i = 0; i < block.getLines().size(); i++) {
                if (i > 0) {
                    page.append('\n');
                }
                page.append(block.getLines().get(i).getText());
            }
        }
        return page.toString().trim();
    }

    synchronized void close() {
        if (recognizer != null) {
            recognizer.close();
            recognizer = null;
        }
    }
}
