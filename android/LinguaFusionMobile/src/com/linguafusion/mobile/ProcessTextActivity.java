package com.linguafusion.mobile;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.ClipData;
import android.content.ClipboardManager;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.res.Configuration;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.os.Bundle;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.view.Window;
import android.view.WindowManager;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;

import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/**
 * Small, on-device translation surface for Android's selected-text menu and
 * text share sheet. Only the text the person deliberately sends is visible to
 * this activity; it needs neither screen capture nor accessibility access.
 */
public final class ProcessTextActivity extends Activity {
    private static final String PREFERENCES = "linguafusion";
    private static final String SOURCE_KEY = "process-text.from";
    private static final String TARGET_KEY = "process-text.to";

    private final ExecutorService executor = Executors.newSingleThreadExecutor();
    private final OfflineTranslation translation = new OfflineTranslation();
    private List<OfflineLanguages.Entry> languages;
    private SharedPreferences preferences;
    private Palette palette;
    private String originalText;
    private String translatedText;
    private String sourceCode;
    private String targetCode;
    private boolean replaceAllowed;
    private boolean destroyed;
    private int translationGeneration;

    private Button sourceButton;
    private Button targetButton;
    private Button translateButton;
    private Button copyButton;
    private Button replaceButton;
    private ProgressBar progress;
    private TextView status;
    private TextView result;
    private TextView routeNote;
    private LinearLayout resultSection;

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        final Intent request = getIntent();
        final boolean processing = request != null
                && Intent.ACTION_PROCESS_TEXT.equals(request.getAction());
        final boolean sharing = request != null
                && Intent.ACTION_SEND.equals(request.getAction());
        final CharSequence supplied = processing
                ? request.getCharSequenceExtra(Intent.EXTRA_PROCESS_TEXT)
                : sharing ? request.getCharSequenceExtra(Intent.EXTRA_TEXT) : null;
        if (supplied == null || supplied.toString().trim().isEmpty()) {
            finish();
            return;
        }

        originalText = supplied.toString();
        // A shared passage and a read-only PROCESS_TEXT request can be copied,
        // but returning a replacement to their caller would be misleading.
        replaceAllowed = processing
                && !request.getBooleanExtra(Intent.EXTRA_PROCESS_TEXT_READONLY, true);
        preferences = getSharedPreferences(PREFERENCES, MODE_PRIVATE);
        languages = OfflineLanguages.all();
        sourceCode = recalledLanguage(SOURCE_KEY,
                recalledLanguage("offline.from", "en"));
        targetCode = recalledLanguage(TARGET_KEY,
                recalledLanguage("offline.to", "de"));
        if (sourceCode.equals(targetCode)) targetCode = fallbackTarget(sourceCode);
        palette = Palette.forConfiguration(getResources().getConfiguration());

        configureWindow();
        setContentView(content());
        translateSelection();
    }

    private void configureWindow() {
        final Window window = getWindow();
        window.setBackgroundDrawableResource(android.R.color.transparent);
        window.addFlags(WindowManager.LayoutParams.FLAG_DIM_BEHIND);
        final WindowManager.LayoutParams attributes = window.getAttributes();
        attributes.dimAmount = 0.42f;
        attributes.gravity = Gravity.CENTER;
        window.setAttributes(attributes);
        setFinishOnTouchOutside(true);
    }

    @Override protected void onResume() {
        super.onResume();
        final Window window = getWindow();
        final WindowManager.LayoutParams attributes = window.getAttributes();
        final int available = getResources().getDisplayMetrics().widthPixels;
        attributes.width = Math.min(available - dp(24), dp(520));
        attributes.height = WindowManager.LayoutParams.WRAP_CONTENT;
        window.setAttributes(attributes);
    }

    private View content() {
        final ScrollView scroll = new ScrollView(this);
        scroll.setFillViewport(false);
        final LinearLayout card = column();
        card.setPadding(dp(22), dp(22), dp(22), dp(18));
        card.setBackground(rounded(palette.surface, 24, palette.line, 1));
        scroll.addView(card, matchWrap());

        final TextView badge = text("ON-DEVICE · PRIVATE", 11, palette.accent, Typeface.BOLD);
        badge.setLetterSpacing(0.08f);
        badge.setGravity(Gravity.CENTER);
        badge.setPadding(dp(10), dp(5), dp(10), dp(5));
        badge.setBackground(rounded(palette.chip, 99, Color.TRANSPARENT, 0));
        final LinearLayout.LayoutParams badgeLayout = wrapWrap();
        badgeLayout.gravity = Gravity.START;
        card.addView(badge, badgeLayout);

        final TextView title = text("Translate with LinguaFusion", 25, palette.text,
                Typeface.create("serif", Typeface.BOLD));
        title.setPadding(0, dp(14), 0, dp(5));
        card.addView(title, matchWrap());
        card.addView(text(replaceAllowed
                ? "Preview the translation, then replace the selected text."
                : "Preview the translation, then copy it back to your conversation.",
                14, palette.muted, Typeface.NORMAL), matchWrap());

        card.addView(sectionLabel("SELECTED TEXT", dp(18)), matchWrap());
        final TextView original = text(originalText, 16, palette.text, Typeface.NORMAL);
        original.setTextDirection(View.TEXT_DIRECTION_FIRST_STRONG);
        original.setMaxLines(7);
        original.setPadding(dp(14), dp(12), dp(14), dp(12));
        original.setBackground(rounded(palette.translation, 14, palette.line, 1));
        card.addView(original, matchWrap());

        card.addView(sectionLabel("LANGUAGES", dp(18)), matchWrap());
        final LinearLayout languageRow = new LinearLayout(this);
        languageRow.setOrientation(LinearLayout.HORIZONTAL);
        languageRow.setGravity(Gravity.CENTER_VERTICAL);
        final LinearLayout source = languageChoice("From");
        sourceButton = languageButton(sourceCode);
        sourceButton.setOnClickListener(view -> chooseLanguage(true));
        source.addView(sourceButton, matchWrap());
        languageRow.addView(source, weighted(1));

        final Button swap = outlinedButton("⇄");
        swap.setContentDescription("Swap source and target languages");
        swap.setTextSize(23);
        final LinearLayout.LayoutParams swapLayout = new LinearLayout.LayoutParams(dp(48), dp(48));
        swapLayout.setMargins(dp(8), dp(18), dp(8), 0);
        languageRow.addView(swap, swapLayout);

        final LinearLayout target = languageChoice("To");
        targetButton = languageButton(targetCode);
        targetButton.setOnClickListener(view -> chooseLanguage(false));
        target.addView(targetButton, matchWrap());
        languageRow.addView(target, weighted(1));
        card.addView(languageRow, matchWrap());
        swap.setOnClickListener(view -> {
            final String oldSource = sourceCode;
            sourceCode = targetCode;
            targetCode = oldSource;
            rememberPair();
            updateLanguageButtons();
            translateSelection();
        });

        translateButton = primaryButton("Translate on this phone");
        translateButton.setOnClickListener(view -> translateSelection());
        card.addView(translateButton, spacedMatchWrap(14));

        final LinearLayout working = new LinearLayout(this);
        working.setOrientation(LinearLayout.HORIZONTAL);
        working.setGravity(Gravity.CENTER_VERTICAL);
        progress = new ProgressBar(this, null, android.R.attr.progressBarStyleSmall);
        progress.setIndeterminateTintList(android.content.res.ColorStateList.valueOf(palette.accent));
        working.addView(progress, new LinearLayout.LayoutParams(dp(28), dp(28)));
        status = text("Translating on this phone…", 14, palette.muted, Typeface.NORMAL);
        status.setPadding(dp(10), 0, 0, 0);
        working.addView(status, weighted(1));
        card.addView(working, spacedMatchWrap(14));

        resultSection = column();
        resultSection.addView(sectionLabel("TRANSLATION", dp(4)), matchWrap());
        result = text("", 18, palette.text, Typeface.NORMAL);
        result.setTextDirection(View.TEXT_DIRECTION_FIRST_STRONG);
        result.setTextIsSelectable(true);
        result.setPadding(dp(14), dp(14), dp(14), dp(14));
        result.setBackground(rounded(palette.translation, 14, palette.line, 1));
        resultSection.addView(result, matchWrap());
        routeNote = text("", 12, palette.muted, Typeface.NORMAL);
        routeNote.setPadding(0, dp(7), 0, 0);
        resultSection.addView(routeNote, matchWrap());
        card.addView(resultSection, spacedMatchWrap(14));
        resultSection.setVisibility(View.GONE);

        if (replaceAllowed) {
            replaceButton = primaryButton("Replace selected text");
            replaceButton.setOnClickListener(view -> replaceSelection());
            card.addView(replaceButton, spacedMatchWrap(14));
        }
        copyButton = outlinedButton(replaceAllowed ? "Copy translation" : "Copy and return");
        copyButton.setOnClickListener(view -> copyTranslation());
        card.addView(copyButton, spacedMatchWrap(replaceAllowed ? 8 : 14));

        final Button close = quietButton("Close");
        close.setOnClickListener(view -> finish());
        card.addView(close, spacedMatchWrap(6));

        final TextView models = text(
                "Uses downloaded Offline language packs. Manage them in LinguaFusion → Offline → Storage.",
                12, palette.muted, Typeface.NORMAL);
        models.setPadding(0, dp(8), 0, 0);
        card.addView(models, matchWrap());
        setResultActionsEnabled(false);
        return scroll;
    }

    private void chooseLanguage(boolean source) {
        final String[] labels = new String[languages.size()];
        int checked = 0;
        final String current = source ? sourceCode : targetCode;
        for (int i = 0; i < languages.size(); i++) {
            labels[i] = languageLabel(languages.get(i));
            if (languages.get(i).code.equals(current)) checked = i;
        }
        new AlertDialog.Builder(this)
                .setTitle(source ? "Translate from" : "Translate to")
                .setSingleChoiceItems(labels, checked, (dialog, which) -> {
                    if (source) sourceCode = languages.get(which).code;
                    else targetCode = languages.get(which).code;
                    rememberPair();
                    updateLanguageButtons();
                    dialog.dismiss();
                    translateSelection();
                })
                .setNegativeButton("Cancel", null)
                .show();
    }

    private void translateSelection() {
        if (sourceCode.equals(targetCode)) {
            showError("Choose two different languages.");
            return;
        }
        rememberPair();
        translatedText = null;
        resultSection.setVisibility(View.GONE);
        setResultActionsEnabled(false);
        translateButton.setEnabled(false);
        translateButton.setAlpha(0.55f);
        progress.setVisibility(View.VISIBLE);
        status.setTextColor(palette.muted);
        status.setText("Translating on this phone…");
        final int generation = ++translationGeneration;
        final String from = sourceCode;
        final String to = targetCode;
        executor.execute(() -> {
            final String answer = translation.translate(originalText, from, to);
            final boolean pivoted = OfflineLanguages.pivotsThroughEnglish(from, to);
            runOnUiThread(() -> {
                if (destroyed || generation != translationGeneration) return;
                translateButton.setEnabled(true);
                translateButton.setAlpha(1f);
                progress.setVisibility(View.GONE);
                if (answer.startsWith("ERROR: ")) {
                    showError(answer.substring(7));
                    return;
                }
                if (answer.trim().isEmpty()) {
                    showError("The phone returned an empty translation. Try again.");
                    return;
                }
                translatedText = answer;
                result.setText(answer);
                routeNote.setText(pivoted
                        ? "Translated through English on this device."
                        : "Translated directly on this device.");
                resultSection.setVisibility(View.VISIBLE);
                status.setTextColor(palette.accent);
                status.setText("Ready to use");
                setResultActionsEnabled(true);
            });
        });
    }

    private void showError(String message) {
        progress.setVisibility(View.GONE);
        translateButton.setEnabled(true);
        translateButton.setAlpha(1f);
        status.setTextColor(palette.danger);
        status.setText(message);
        resultSection.setVisibility(View.GONE);
        setResultActionsEnabled(false);
    }

    private void replaceSelection() {
        if (!replaceAllowed || translatedText == null) return;
        final Intent answer = new Intent();
        answer.putExtra(Intent.EXTRA_PROCESS_TEXT, translatedText);
        setResult(RESULT_OK, answer);
        finish();
    }

    private void copyTranslation() {
        if (translatedText == null) return;
        final ClipboardManager clipboard =
                (ClipboardManager) getSystemService(Context.CLIPBOARD_SERVICE);
        clipboard.setPrimaryClip(ClipData.newPlainText("LinguaFusion translation", translatedText));
        Toast.makeText(this, "Translation copied", Toast.LENGTH_SHORT).show();
        if (!replaceAllowed) finish();
    }

    private String recalledLanguage(String key, String fallback) {
        final String saved = preferences.getString(key, fallback);
        return OfflineLanguages.isSupported(saved)
                ? OfflineLanguages.normalise(saved) : fallback;
    }

    private String fallbackTarget(String source) {
        return "en".equals(source) ? "de" : "en";
    }

    private void rememberPair() {
        preferences.edit().putString(SOURCE_KEY, sourceCode)
                .putString(TARGET_KEY, targetCode).apply();
    }

    private void updateLanguageButtons() {
        sourceButton.setText(languageName(sourceCode));
        targetButton.setText(languageName(targetCode));
    }

    private String languageName(String code) {
        final OfflineLanguages.Entry entry = OfflineLanguages.find(code);
        return entry == null ? code : entry.nativeName;
    }

    private String languageLabel(OfflineLanguages.Entry entry) {
        return entry.englishName.equals(entry.nativeName)
                ? entry.englishName : entry.nativeName + " · " + entry.englishName;
    }

    private LinearLayout languageChoice(String label) {
        final LinearLayout group = column();
        group.addView(text(label, 12, palette.muted, Typeface.BOLD), matchWrap());
        return group;
    }

    private Button languageButton(String code) {
        final Button button = outlinedButton(languageName(code));
        button.setGravity(Gravity.START | Gravity.CENTER_VERTICAL);
        return button;
    }

    private TextView sectionLabel(String value, int top) {
        final TextView label = text(value, 11, palette.muted, Typeface.BOLD);
        label.setLetterSpacing(0.08f);
        label.setPadding(0, top, 0, dp(7));
        return label;
    }

    private Button primaryButton(String value) {
        final Button button = baseButton(value);
        button.setTextColor(palette.onAccent);
        button.setBackground(rounded(palette.accent, 12, Color.TRANSPARENT, 0));
        return button;
    }

    private Button outlinedButton(String value) {
        final Button button = baseButton(value);
        button.setTextColor(palette.text);
        button.setBackground(rounded(palette.surface, 12, palette.line, 1));
        return button;
    }

    private Button quietButton(String value) {
        final Button button = baseButton(value);
        button.setTextColor(palette.muted);
        button.setBackgroundColor(Color.TRANSPARENT);
        return button;
    }

    private Button baseButton(String value) {
        final Button button = new Button(this);
        button.setText(value);
        button.setTextSize(15);
        button.setAllCaps(false);
        button.setTypeface(Typeface.create("sans", Typeface.BOLD));
        button.setGravity(Gravity.CENTER);
        button.setMinHeight(dp(48));
        button.setPadding(dp(13), dp(8), dp(13), dp(8));
        button.setStateListAnimator(null);
        return button;
    }

    private TextView text(String value, float size, int color, Typeface face) {
        final TextView text = new TextView(this);
        text.setText(value);
        text.setTextSize(size);
        text.setTextColor(color);
        text.setTypeface(face);
        text.setLineSpacing(0, 1.12f);
        return text;
    }

    private TextView text(String value, float size, int color, int style) {
        return text(value, size, color, Typeface.create("sans", style));
    }

    private LinearLayout column() {
        final LinearLayout layout = new LinearLayout(this);
        layout.setOrientation(LinearLayout.VERTICAL);
        return layout;
    }

    private GradientDrawable rounded(int fill, int radius, int stroke, int strokeWidth) {
        final GradientDrawable shape = new GradientDrawable();
        shape.setColor(fill);
        shape.setCornerRadius(dp(radius));
        if (strokeWidth > 0) shape.setStroke(dp(strokeWidth), stroke);
        return shape;
    }

    private LinearLayout.LayoutParams matchWrap() {
        return new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
    }

    private LinearLayout.LayoutParams wrapWrap() {
        return new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT);
    }

    private LinearLayout.LayoutParams weighted(float weight) {
        return new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, weight);
    }

    private LinearLayout.LayoutParams spacedMatchWrap(int top) {
        final LinearLayout.LayoutParams layout = matchWrap();
        layout.topMargin = dp(top);
        return layout;
    }

    private void setResultActionsEnabled(boolean enabled) {
        if (replaceButton != null) {
            replaceButton.setEnabled(enabled);
            replaceButton.setAlpha(enabled ? 1f : 0.45f);
        }
        if (copyButton != null) {
            copyButton.setEnabled(enabled);
            copyButton.setAlpha(enabled ? 1f : 0.45f);
        }
    }

    private int dp(int value) {
        return Math.round(value * getResources().getDisplayMetrics().density);
    }

    @Override protected void onDestroy() {
        destroyed = true;
        translationGeneration++;
        executor.shutdownNow();
        translation.close();
        super.onDestroy();
    }

    private static final class Palette {
        final int surface;
        final int text;
        final int muted;
        final int accent;
        final int onAccent;
        final int line;
        final int chip;
        final int translation;
        final int danger;

        Palette(String surface, String text, String muted, String accent,
                String onAccent, String line, String chip, String translation,
                String danger) {
            this.surface = Color.parseColor(surface);
            this.text = Color.parseColor(text);
            this.muted = Color.parseColor(muted);
            this.accent = Color.parseColor(accent);
            this.onAccent = Color.parseColor(onAccent);
            this.line = Color.parseColor(line);
            this.chip = Color.parseColor(chip);
            this.translation = Color.parseColor(translation);
            this.danger = Color.parseColor(danger);
        }

        static Palette forConfiguration(Configuration configuration) {
            final boolean night = (configuration.uiMode & Configuration.UI_MODE_NIGHT_MASK)
                    == Configuration.UI_MODE_NIGHT_YES;
            return night
                    ? new Palette("#261820", "#FCE8EC", "#C3AAB2", "#F24E7A",
                            "#1A1015", "#674152", "#3D2432", "#331D2A", "#FFB4AB")
                    : new Palette("#FCF9F2", "#2B2622", "#716553", "#B04A2F",
                            "#FFFFFF", "#D8CFBD", "#EEE1CD", "#EEE6D6", "#A52D26");
        }
    }
}
