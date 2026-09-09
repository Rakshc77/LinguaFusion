package com.linguafusion.mobile;

import android.Manifest;
import android.app.Activity;
import android.app.AlertDialog;
import android.os.Handler;
import android.os.Looper;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.graphics.Color;
import android.graphics.Insets;
import android.graphics.drawable.GradientDrawable;
import android.media.AudioFormat;
import android.media.AudioRecord;
import android.media.MediaRecorder;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.provider.Settings;
import android.util.Base64;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.view.WindowInsets;
import android.webkit.JavascriptInterface;
import android.webkit.PermissionRequest;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceResponse;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Button;
import android.widget.EditText;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;

import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileOutputStream;
import java.io.InputStreamReader;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.util.Objects;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public final class MainActivity extends Activity {
    private static final int FILE_REQUEST = 41;
    private static final int AUDIO_PERMISSION = 42;
    private final ExecutorService executor = Executors.newSingleThreadExecutor();
    private SharedPreferences preferences;
    private WebView webView;
    private FrameLayout insetRoot;
    private boolean darkSystemBars;
    private ValueCallback<Uri[]> fileCallback;
    private PermissionRequest pendingAudioRequest;
    private AlertDialog cloudRecorderDialog;
    private final Handler recordingHandler = new Handler(Looper.getMainLooper());
    private Runnable cloudRecordingTimeout;
    private final Object nativeAudioLock = new Object();
    private volatile boolean nativeAudioRecording;
    private AudioRecord nativeAudioRecord;
    private Thread nativeAudioThread;
    private File nativeAudioFile;
    private static final int NATIVE_SAMPLE_RATE = 16000;
    // Owner-hosted cloud service. Unlike PC mode this needs no pairing key:
    // the page signs in with Firebase and the owner approves each account.
    private static final String CLOUD_BASE = "https://linguafusion-cloud-pilot-jl77ipbeua-ey.a.run.app";
    private static final String OFFLINE_PAGE = "file:///android_asset/offline/index.html";
    /** Five minutes. Long enough for anything spoken in one go, short
     *  enough that the float array it becomes still fits in memory. */
    private static final int OFFLINE_RECORDING_SECONDS = 300;
    private OfflineSpeech offlineSpeech;
    private OfflineTranslation offlineTranslation;

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        applySystemBarTheme(false);
        preferences = getSharedPreferences("linguafusion", MODE_PRIVATE);
        if (handlePairingIntent(getIntent())) return;
        if ("cloud".equals(preferences.getString("mode", ""))) { showCloudApp(); return; }
        if ("offline".equals(preferences.getString("mode", ""))) { showOfflineApp(); return; }
        String server = preferences.getString("server", "");
        if (server.isEmpty()) showConnectionScreen(); else verifySavedConnection(server, preferences.getString("key", ""));
    }

    @Override protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        setIntent(intent);
        handlePairingIntent(intent);
    }

    private boolean handlePairingIntent(Intent intent) {
        Uri uri = intent == null ? null : intent.getData();
        if (uri == null || !"linguafusion".equalsIgnoreCase(uri.getScheme()) || !"pair".equalsIgnoreCase(uri.getHost())) return false;
        String server = uri.getQueryParameter("server");
        String token = uri.getQueryParameter("token");
        setIntent(new Intent(this,MainActivity.class));
        if (server == null) server = "";
        server = server.trim().replaceAll("/+$", "");
        if ((!server.startsWith("http://") && !server.startsWith("https://")) || token == null || token.trim().isEmpty()) {
            showConnectionScreen();
            Toast.makeText(this, "This pairing QR code is invalid. Create a fresh one on the PC.", Toast.LENGTH_LONG).show();
            return true;
        }
        final String pairingServer = server;
        final String pairingToken = token.trim();
        showConnectingScreen(pairingServer);
        executor.execute(() -> {
            try {
                JSONObject paired = postJson(pairingServer + "/pair", new JSONObject()
                    .put("token", pairingToken)
                    .put("device_name", Build.MANUFACTURER + " " + Build.MODEL)
                    .put("platform", "android"));
                String apiKey = paired.optString("api_key", "").trim();
                if (apiKey.isEmpty()) throw new java.io.IOException("The PC did not return a pairing key.");
                String connectionError = testServer(pairingServer, apiKey);
                if (connectionError != null) throw new java.io.IOException(connectionError);
                preferences.edit().putString("server", pairingServer).putString("key", apiKey).apply();
                runOnUiThread(() -> {
                    Toast.makeText(this, "Phone paired. It will reconnect automatically.", Toast.LENGTH_LONG).show();
                    showWebApp(pairingServer, apiKey);
                });
            } catch (Exception error) {
                runOnUiThread(() -> {
                    showConnectionScreen();
                    Toast.makeText(this, "Pairing failed: " + error.getMessage(), Toast.LENGTH_LONG).show();
                });
            }
        });
        return true;
    }

    private int dp(int value) { return Math.round(value * getResources().getDisplayMetrics().density); }
    private int systemBarBackground() {
        return darkSystemBars ? Color.rgb(17,21,27) : Color.rgb(246,248,252);
    }
    private void applySystemBarTheme(boolean dark) {
        darkSystemBars = dark;
        int color = systemBarBackground();
        getWindow().setStatusBarColor(color);
        getWindow().setNavigationBarColor(color);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            getWindow().setStatusBarContrastEnforced(false);
            getWindow().setNavigationBarContrastEnforced(false);
        }
        int flags = getWindow().getDecorView().getSystemUiVisibility();
        flags &= ~View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR;
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            flags &= ~View.SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR;
        }
        if (!dark) {
            flags |= View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR;
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                flags |= View.SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR;
            }
        }
        getWindow().getDecorView().setSystemUiVisibility(flags);
        if (insetRoot != null) insetRoot.setBackgroundColor(color);
        if (webView != null) webView.setBackgroundColor(color);
    }
    private void setInsetContentView(View content) {
        FrameLayout root = new FrameLayout(this);
        root.setBackgroundColor(systemBarBackground());
        root.addView(content, new FrameLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT));
        root.setOnApplyWindowInsetsListener((view, windowInsets) -> {
            int left;
            int top;
            int right;
            int bottom;
            WindowInsets childInsets;
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
                int insetTypes = WindowInsets.Type.systemBars() | WindowInsets.Type.displayCutout();
                Insets safe = windowInsets.getInsets(insetTypes);
                left = safe.left;
                top = safe.top;
                right = safe.right;
                bottom = safe.bottom;
                childInsets = new WindowInsets.Builder(windowInsets)
                    .setInsets(insetTypes, Insets.NONE)
                    .build();
            } else {
                left = windowInsets.getSystemWindowInsetLeft();
                top = windowInsets.getSystemWindowInsetTop();
                right = windowInsets.getSystemWindowInsetRight();
                bottom = windowInsets.getSystemWindowInsetBottom();
                childInsets = windowInsets.replaceSystemWindowInsets(0, 0, 0, 0);
            }
            view.setPadding(left, top, right, bottom);
            return childInsets;
        });
        insetRoot = root;
        setContentView(root);
        root.requestApplyInsets();
    }
    private GradientDrawable background(int color, int stroke, int radius) {
        GradientDrawable drawable = new GradientDrawable(); drawable.setColor(color); drawable.setCornerRadius(dp(radius));
        if (stroke != Color.TRANSPARENT) drawable.setStroke(dp(1), stroke); return drawable;
    }
    private TextView text(String value, int size, boolean bold) {
        TextView view = new TextView(this); view.setText(value); view.setTextColor(Color.rgb(23,32,51)); view.setTextSize(size);
        if (bold) view.setTypeface(view.getTypeface(), android.graphics.Typeface.BOLD); return view;
    }
    private void margin(View view, int top) {
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        params.topMargin = dp(top); view.setLayoutParams(params);
    }

    private void showConnectionScreen() {
        releaseWebView();
        applySystemBarTheme(false);
        ScrollView scroll = new ScrollView(this); scroll.setFillViewport(true); scroll.setBackgroundColor(Color.rgb(246,248,252));
        LinearLayout root = new LinearLayout(this); root.setOrientation(LinearLayout.VERTICAL); root.setPadding(dp(24), dp(54), dp(24), dp(32)); scroll.addView(root);
        TextView mark = text("文", 26, true); mark.setTextColor(Color.rgb(11,87,208)); mark.setGravity(Gravity.CENTER); mark.setBackground(background(Color.rgb(232,240,254), Color.TRANSPARENT, 12));
        root.addView(mark, new LinearLayout.LayoutParams(dp(54), dp(54)));
        TextView title = text("Connect LinguaFusion", 28, true); margin(title, 22); root.addView(title);
        TextView subtitle = text("Use your PC's GPU and offline language models from this phone.", 15, false); subtitle.setTextColor(Color.rgb(102,112,133)); margin(subtitle, 8); root.addView(subtitle);

        LinearLayout card = new LinearLayout(this); card.setOrientation(LinearLayout.VERTICAL); card.setPadding(dp(18),dp(18),dp(18),dp(18)); card.setBackground(background(Color.WHITE,Color.rgb(215,222,232),14)); margin(card, 26); root.addView(card);
        TextView serverLabel=text("PC address",13,true); card.addView(serverLabel);
        EditText serverInput=new EditText(this); serverInput.setSingleLine(true); serverInput.setHint("http://192.168.1.20:8000"); serverInput.setText(preferences.getString("server","")); serverInput.setInputType(android.text.InputType.TYPE_CLASS_TEXT|android.text.InputType.TYPE_TEXT_VARIATION_URI); margin(serverInput,6); card.addView(serverInput);
        TextView keyLabel=text("Pairing key",13,true); margin(keyLabel,16); card.addView(keyLabel);
        EditText keyInput=new EditText(this); keyInput.setSingleLine(true); keyInput.setHint("Shown on the PC"); keyInput.setText(preferences.getString("key","")); keyInput.setInputType(android.text.InputType.TYPE_CLASS_TEXT|android.text.InputType.TYPE_TEXT_VARIATION_PASSWORD); margin(keyInput,6); card.addView(keyInput);
        Button connect=new Button(this); connect.setText("Connect to PC"); connect.setTextColor(Color.WHITE); connect.setTextSize(15); connect.setAllCaps(false); connect.setBackground(background(Color.rgb(11,87,208),Color.TRANSPARENT,10)); margin(connect,20); card.addView(connect,new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT,dp(50)));
        TextView help=text("Scan a one-time invitation from the owner to connect over HTTPS from anywhere, or use the private-network backend address.",13,false); help.setTextColor(Color.rgb(102,112,133)); margin(help,18); root.addView(help);

        TextView cloudTitle=text("No PC to connect to?",15,true); margin(cloudTitle,26); root.addView(cloudTitle);
        TextView cloudHelp=text("Use the owner's cloud service instead: translation, pronunciation guides, speech and reading text from pictures. You create an account and the owner approves it by hand. No pairing key needed.",13,false); cloudHelp.setTextColor(Color.rgb(102,112,133)); margin(cloudHelp,6); root.addView(cloudHelp);
        Button cloudButton=new Button(this); cloudButton.setText("Use LinguaFusion Cloud"); cloudButton.setTextSize(15); cloudButton.setAllCaps(false); cloudButton.setTextColor(Color.rgb(11,87,208)); cloudButton.setBackground(background(Color.WHITE,Color.rgb(11,87,208),10)); margin(cloudButton,14); root.addView(cloudButton,new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT,dp(50)));
        TextView offlineTitle=text("No signal either?",15,true); margin(offlineTitle,26); root.addView(offlineTitle);
        TextView offlineHelp=text("Work entirely on this phone: speech and translation for English, German, Arabic, Spanish and French. Download the language files once over Wi-Fi and it keeps working with no signal, no account and no cost.",13,false); offlineHelp.setTextColor(Color.rgb(102,112,133)); margin(offlineHelp,6); root.addView(offlineHelp);
        Button offlineButton=new Button(this); offlineButton.setText("Work offline on this phone"); offlineButton.setTextSize(15); offlineButton.setAllCaps(false); offlineButton.setTextColor(Color.rgb(11,87,208)); offlineButton.setBackground(background(Color.WHITE,Color.rgb(11,87,208),10)); margin(offlineButton,14); root.addView(offlineButton,new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT,dp(50)));
        offlineButton.setOnClickListener(view -> {
            // No server and no key: offline mode talks to nothing. Clearing
            // them also stops isTrustedOrigin() from treating a stale cloud
            // origin as trusted while the phone is in offline mode.
            preferences.edit().putString("mode","offline").putString("server","").putString("key","").apply();
            showOfflineApp();
        });
        cloudButton.setOnClickListener(view -> {
            // isTrustedOrigin() checks the microphone request against "server",
            // so the cloud origin is recorded there. The pairing key stays empty:
            // cloud access is granted by Firebase sign-in plus owner approval.
            preferences.edit().putString("mode","cloud").putString("server",CLOUD_BASE).putString("key","").apply();
            showCloudApp();
        });
        connect.setOnClickListener(view -> {
            String server=serverInput.getText().toString().trim().replaceAll("/+$",""); String key=keyInput.getText().toString().trim();
            if (!server.startsWith("http://") && !server.startsWith("https://")) { Toast.makeText(this,"Enter the full http:// or https:// address.",Toast.LENGTH_LONG).show(); return; }
            connect.setEnabled(false); connect.setText("Testing connection…");
            executor.execute(() -> {
                String error = testServer(server, key);
                runOnUiThread(() -> { connect.setEnabled(true); connect.setText("Connect to PC"); if(error==null){preferences.edit().putString("server",server).putString("key",key).apply();showWebApp(server,key);}else Toast.makeText(this,error,Toast.LENGTH_LONG).show(); });
            });
        });
        setInsetContentView(scroll);
    }

    private void verifySavedConnection(String server,String key){
        showConnectingScreen(server);
        executor.execute(() -> {
            String error=testServer(server,key);
            runOnUiThread(() -> {if(error==null)showWebApp(server,key);else showBackendUnavailable(server,key,error);});
        });
    }

    private void showConnectingScreen(String server){
        releaseWebView();
        applySystemBarTheme(false);
        LinearLayout root=new LinearLayout(this);root.setOrientation(LinearLayout.VERTICAL);root.setGravity(Gravity.CENTER);root.setPadding(dp(28),dp(40),dp(28),dp(40));root.setBackgroundColor(Color.rgb(246,248,252));
        ProgressBar progress=new ProgressBar(this);root.addView(progress,new LinearLayout.LayoutParams(dp(46),dp(46)));
        TextView title=text("Connecting to your PC",22,true);title.setGravity(Gravity.CENTER);margin(title,20);root.addView(title);
        TextView address=text(server,13,false);address.setTextColor(Color.rgb(102,112,133));address.setGravity(Gravity.CENTER);margin(address,6);root.addView(address);
        setInsetContentView(root);
    }

    private void showBackendUnavailable(String server,String key,String detail){
        releaseWebView();
        applySystemBarTheme(false);
        ScrollView scroll=new ScrollView(this);scroll.setFillViewport(true);scroll.setBackgroundColor(Color.rgb(246,248,252));
        LinearLayout root=new LinearLayout(this);root.setOrientation(LinearLayout.VERTICAL);root.setGravity(Gravity.CENTER_HORIZONTAL);root.setPadding(dp(24),dp(70),dp(24),dp(36));scroll.addView(root);
        TextView mark=text("!",26,true);mark.setTextColor(Color.rgb(160,78,0));mark.setGravity(Gravity.CENTER);mark.setBackground(background(Color.rgb(255,241,214),Color.TRANSPARENT,12));root.addView(mark,new LinearLayout.LayoutParams(dp(54),dp(54)));
        boolean paused=detail!=null&&detail.toLowerCase().contains("access paused");
        TextView title=text(paused?"Access paused by owner":"PC backend is offline",26,true);title.setGravity(Gravity.CENTER);margin(title,22);root.addView(title);
        TextView message=text(paused?"Your pairing is still saved. The owner can restore this device from Friend access control.":"Start LinguaFusion on the PC and keep the backend window open. Your saved pairing is still available.",15,false);message.setTextColor(Color.rgb(102,112,133));message.setGravity(Gravity.CENTER);margin(message,9);root.addView(message);
        TextView reason=text(detail,12,false);reason.setTextColor(Color.rgb(130,84,20));reason.setGravity(Gravity.CENTER);margin(reason,14);root.addView(reason);
        Button retry=new Button(this);retry.setText("Retry connection");retry.setTextColor(Color.WHITE);retry.setAllCaps(false);retry.setBackground(background(Color.rgb(11,87,208),Color.TRANSPARENT,10));margin(retry,26);root.addView(retry,new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT,dp(50)));
        Button change=new Button(this);change.setText("Change PC or pairing");change.setAllCaps(false);change.setBackground(background(Color.WHITE,Color.rgb(215,222,232),10));margin(change,10);root.addView(change,new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT,dp(48)));
        retry.setOnClickListener(view -> verifySavedConnection(server,key));
        change.setOnClickListener(view -> showConnectionScreen());
        setInsetContentView(scroll);
    }

    private String testServer(String server, String key) {
        try {
            JSONObject root=getJson(server+"/",key);
            if(!root.optBoolean("ok"))return "This does not look like a LinguaFusion backend.";
            if(root.optBoolean("auth_required")){
                if(key.isEmpty())return "This phone is not paired yet. Scan a fresh QR code or enter the pairing key.";
                try{getJson(server+"/diagnostics",key);}catch(Exception authError){String detail=authError.getMessage();if(detail!=null&&detail.toLowerCase().contains("access paused"))return "Access paused by the LinguaFusion owner.";return "The saved pairing is no longer valid. Pair this phone again.";}
            }
            return null;
        } catch(Exception error) { return "Could not reach the PC: "+error.getMessage(); }
    }

    private JSONObject getJson(String address,String key)throws Exception{
        HttpURLConnection connection=(HttpURLConnection)new URL(address).openConnection();
        try{
            connection.setConnectTimeout(5000);connection.setReadTimeout(5000);if(!key.isEmpty())connection.setRequestProperty("X-API-Key",key);
            int status=connection.getResponseCode();java.io.InputStream stream=status>=200&&status<300?connection.getInputStream():connection.getErrorStream();StringBuilder json=new StringBuilder();
            if(stream!=null)try(BufferedReader reader=new BufferedReader(new InputStreamReader(stream,StandardCharsets.UTF_8))){for(String line;(line=reader.readLine())!=null;)json.append(line);}
            if(status<200||status>=300){
                String detail="HTTP "+status;
                try{if(json.length()>0)detail=new JSONObject(json.toString()).optString("detail",detail);}catch(Exception ignored){}
                if(status==502||status==503||status==504)detail="The PC backend is offline (HTTP "+status+"). Start LinguaFusion on the PC and retry.";
                throw new java.io.IOException(detail);
            }
            JSONObject result=json.length()==0?new JSONObject():new JSONObject(json.toString());
            return result;
        }finally{connection.disconnect();}
    }

    private JSONObject postJson(String address, JSONObject payload)throws Exception{
        HttpURLConnection connection=(HttpURLConnection)new URL(address).openConnection();
        try{
            connection.setConnectTimeout(5000);connection.setReadTimeout(5000);connection.setRequestMethod("POST");connection.setDoOutput(true);connection.setRequestProperty("Content-Type","application/json; charset=utf-8");
            byte[] body=payload.toString().getBytes(StandardCharsets.UTF_8);connection.setFixedLengthStreamingMode(body.length);
            try(java.io.OutputStream output=connection.getOutputStream()){output.write(body);}
            int status=connection.getResponseCode();java.io.InputStream stream=status>=200&&status<300?connection.getInputStream():connection.getErrorStream();StringBuilder json=new StringBuilder();
            if(stream!=null)try(BufferedReader reader=new BufferedReader(new InputStreamReader(stream,StandardCharsets.UTF_8))){for(String line;(line=reader.readLine())!=null;)json.append(line);}
            JSONObject result=json.length()==0?new JSONObject():new JSONObject(json.toString());
            if(status<200||status>=300)throw new java.io.IOException(result.optString("detail","HTTP "+status));
            return result;
        }finally{connection.disconnect();}
    }

    private void showWebApp(String server, String key) {
        applySystemBarTheme(false);
        webView=newWebViewWithMediaSupport();
        webView.addJavascriptInterface(new NativeBridge(),"LinguaFusionNative");
        webView.setWebViewClient(new WebViewClient(){
            private boolean connectionInjected=false;
            @Override public void onPageFinished(WebView view,String url){
                super.onPageFinished(view,url);
                if(connectionInjected||url==null||!url.startsWith(server))return;
                connectionInjected=true;
                String script="localStorage.setItem('lf.server',"+jsQuote(server)+");"
                    +"localStorage.setItem('lf.key',"+jsQuote(key)+");"
                    +"location.replace("+jsQuote(server+"/mobile/")+");";
                view.evaluateJavascript(script,null);
            }
            @Override public void onReceivedError(WebView view,WebResourceRequest request,WebResourceError error){
                super.onReceivedError(view,request,error);
                if(request.isForMainFrame())view.post(() -> {if(view==webView)showBackendUnavailable(server,key,"The mobile page could not load: "+error.getDescription());});
            }
            @Override public void onReceivedHttpError(WebView view,WebResourceRequest request,WebResourceResponse response){
                super.onReceivedHttpError(view,request,response);
                if(request.isForMainFrame()&&response.getStatusCode()>=400)view.post(() -> {if(view==webView)showBackendUnavailable(server,key,"The PC returned HTTP "+response.getStatusCode()+" for the mobile page.");});
            }
        });
        webView.loadUrl(server+"/mobile/"); setInsetContentView(webView);
    }

    /** A WebView that can reach the microphone and the file picker.
     *  Shared by PC and cloud modes so both behave identically for speech and
     *  for choosing a picture; only the caller decides what to load. */
    private WebView newWebViewWithMediaSupport(){
        WebView view=new WebView(this); view.setBackgroundColor(Color.rgb(246,248,252));
        WebSettings settings=view.getSettings(); settings.setJavaScriptEnabled(true);settings.setDomStorageEnabled(true);settings.setMediaPlaybackRequiresUserGesture(false);settings.setAllowFileAccess(true);settings.setAllowContentAccess(true);
        view.setWebChromeClient(new WebChromeClient(){
            @Override public void onPermissionRequest(PermissionRequest request){
                runOnUiThread(() -> {
                    if(!isTrustedOrigin(request.getOrigin()) || !requestsAudioOnly(request)){
                        request.deny();
                        return;
                    }
                    if(getApplicationContext().checkSelfPermission(Manifest.permission.RECORD_AUDIO)==PackageManager.PERMISSION_GRANTED){
                        request.grant(new String[]{PermissionRequest.RESOURCE_AUDIO_CAPTURE});
                    }else{
                        pendingAudioRequest=request;
                        requestPermissions(new String[]{Manifest.permission.RECORD_AUDIO},AUDIO_PERMISSION);
                    }
                });
            }
            @Override public void onPermissionRequestCanceled(PermissionRequest request){
                if(request==pendingAudioRequest)pendingAudioRequest=null;
            }
            @Override public boolean onShowFileChooser(WebView view,ValueCallback<Uri[]> callback,FileChooserParams params){
                if(fileCallback!=null)fileCallback.onReceiveValue(null);fileCallback=callback;try{startActivityForResult(params.createIntent(),FILE_REQUEST);}catch(Exception error){fileCallback=null;Toast.makeText(MainActivity.this,"No file picker is available.",Toast.LENGTH_LONG).show();return false;}return true;
            }
        });
        return view;
    }

    /** Everything on this phone, with no network at all.
     *
     *  Unlike the cloud screen this one DOES get a JavaScript interface, and
     *  the difference is deliberate: this page ships inside the APK, so its
     *  content is ours. To keep it that way the WebView refuses to navigate
     *  anywhere but the bundled assets -- were it ever to load a remote page,
     *  that page would inherit the microphone and file access below. */
    private void showOfflineApp(){
        applySystemBarTheme(false);
        releaseWebView();
        if(offlineSpeech==null)offlineSpeech=new OfflineSpeech(this);
        if(offlineTranslation==null)offlineTranslation=new OfflineTranslation();
        webView=newWebViewWithMediaSupport();
        webView.getSettings().setAllowFileAccess(false);
        webView.getSettings().setAllowContentAccess(false);
        webView.addJavascriptInterface(new OfflineBridge(new OfflineHost(),executor,offlineSpeech,offlineTranslation),"LinguaFusionOffline");
        webView.setWebViewClient(new WebViewClient(){
            @Override public boolean shouldOverrideUrlLoading(WebView view,WebResourceRequest request){
                Uri target=request.getUrl();
                if(isBundledAsset(target))return false;
                // Anything else opens in the real browser. The interface above
                // must never be exposed to a page we did not ship.
                try{startActivity(new Intent(Intent.ACTION_VIEW,target));}catch(Exception ignored){}
                return true;
            }
        });
        webView.loadUrl(OFFLINE_PAGE); setInsetContentView(webView);
    }

    private static boolean isBundledAsset(Uri target){
        return target!=null && "file".equalsIgnoreCase(target.getScheme())
            && target.getPath()!=null && target.getPath().startsWith("/android_asset/offline/");
    }

    /** The small surface OfflineBridge is allowed to reach back through. */
    private final class OfflineHost implements OfflineBridge.Host {
        @Override public byte[] takeRecordedPcm(){return stopNativeAudioRecordingToPcm();}
        @Override public String startRecording(){
            String result=startNativeAudioRecording();
            if("OK".equals(result))return null;
            // PERMISSION_REQUIRED means the dialog is up and nothing is
            // recording. Reporting success here would leave the page saying
            // "speak now" over a microphone that was never opened.
            if("PERMISSION_REQUIRED".equals(result))
                return "Allow the microphone, then press record again.";
            if(result!=null&&result.startsWith("ERROR: "))return result.substring(7);
            return "The microphone could not be started.";
        }
        @Override public void cancelRecording(){cancelNativeAudioRecording();}
        @Override public void resolve(String requestId,String json){
            runOnUiThread(() -> {
                if(webView==null)return;
                // JSON.parse on the page side, so the payload is data and
                // never script, however it was built.
                webView.evaluateJavascript(
                    "window.LF&&window.LF.resolve("+JSONObject.quote(requestId)+","+JSONObject.quote(json)+")",null);
            });
        }
        @Override public void remember(String key,String value){preferences.edit().putString(key,value).apply();}
        @Override public String recall(String key,String fallback){return preferences.getString(key,fallback);}
        @Override public void leaveOfflineMode(){
            runOnUiThread(() -> {
                preferences.edit().remove("mode").apply();
                if(offlineSpeech!=null)offlineSpeech.unload();
                showConnectionScreen();
            });
        }
    }

    /** The owner-hosted cloud service.
     *  Deliberately WITHOUT addJavascriptInterface: the native bridge can wipe
     *  saved settings and drive the microphone directly, and a remotely served
     *  page has no business holding that. Cloud recording uses an explicit
     *  native confirmation dialog, not a JavaScript interface. */
    private void showCloudApp(){
        applySystemBarTheme(false);
        releaseWebView();
        webView=newWebViewWithMediaSupport();
        webView.setWebViewClient(new WebViewClient(){
            @Override public boolean shouldOverrideUrlLoading(WebView view,WebResourceRequest request){
                Uri target=request.getUrl();
                if("linguafusion-record".equals(target.getScheme())){
                    if(request.isForMainFrame() && request.hasGesture()
                            && isCloudOrigin(Uri.parse(view.getUrl()==null?"":view.getUrl()))) {
                        showCloudRecorder(view, target.getQueryParameter("id"));
                    }
                    return true;
                }
                if(isCloudOrigin(target))return false;
                // Sign-in and confirmation links belong in the real browser,
                // not inside this WebView.
                try{startActivity(new Intent(Intent.ACTION_VIEW,target));}catch(Exception ignored){}
                return true;
            }
            @Override public void onPageFinished(WebView view,String url){
                if(view==webView && isCloudOrigin(Uri.parse(url)))
                    view.evaluateJavascript("window.LFNativeCloudRecording=true;",null);
            }
            @Override public void onReceivedError(WebView view,WebResourceRequest request,WebResourceError error){
                super.onReceivedError(view,request,error);
                if(request.isForMainFrame())view.post(() -> {if(view==webView)showCloudUnavailable(String.valueOf(error.getDescription()));});
            }
            @Override public void onReceivedHttpError(WebView view,WebResourceRequest request,WebResourceResponse response){
                super.onReceivedHttpError(view,request,response);
                if(request.isForMainFrame()&&response.getStatusCode()>=400)view.post(() -> {if(view==webView)showCloudUnavailable("The service returned HTTP "+response.getStatusCode()+".");});
            }
        });
        // A WebView never fires this for blob: URLs, so the page emits a data:
        // URL when it detects a WebView. Without this, Download does nothing at
        // all and the person is left thinking the app is broken.
        webView.setDownloadListener((url, agent, disposition, mime, size) -> saveDataUrl(url, disposition));
        webView.loadUrl(CLOUD_BASE+"/pilot/"); setInsetContentView(webView);
    }

    /** Write a data: URL into the public Downloads folder. */
    private void saveDataUrl(String url, String disposition){
        if(url == null || !url.startsWith("data:")){
            Toast.makeText(this,"This download type is not supported in the app. Use the website.",Toast.LENGTH_LONG).show();
            return;
        }
        try{
            int comma = url.indexOf(',');
            if(comma < 0) throw new java.io.IOException("Malformed download.");
            String header = url.substring(5, comma);
            byte[] bytes = header.contains("base64")
                ? Base64.decode(url.substring(comma + 1), Base64.DEFAULT)
                : java.net.URLDecoder.decode(url.substring(comma + 1), "UTF-8").getBytes("UTF-8");
            // Refuse anything implausible for a text export rather than filling
            // storage from a page we do not control.
            if(bytes.length > 8 * 1024 * 1024) throw new java.io.IOException("That file is too large to save.");

            String name = fileNameFrom(disposition, header);
            String mime = header.contains(";") ? header.substring(0, header.indexOf(';')) : header;
            if(mime.isEmpty()) mime = "text/plain";

            if(android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.Q){
                // Scoped storage: writing to the public Downloads PATH fails on
                // Android 10 and later. MediaStore is the supported route and
                // needs no storage permission at all.
                android.content.ContentValues values = new android.content.ContentValues();
                values.put(android.provider.MediaStore.MediaColumns.DISPLAY_NAME, name);
                values.put(android.provider.MediaStore.MediaColumns.MIME_TYPE, mime);
                values.put(android.provider.MediaStore.MediaColumns.RELATIVE_PATH,
                           android.os.Environment.DIRECTORY_DOWNLOADS);
                Uri item = getContentResolver().insert(
                    android.provider.MediaStore.Downloads.EXTERNAL_CONTENT_URI, values);
                if(item == null) throw new java.io.IOException("The Downloads folder refused the file.");
                try(java.io.OutputStream out = getContentResolver().openOutputStream(item)){
                    if(out == null) throw new java.io.IOException("The file could not be opened for writing.");
                    out.write(bytes);
                }
            }else{
                File folder = android.os.Environment.getExternalStoragePublicDirectory(
                    android.os.Environment.DIRECTORY_DOWNLOADS);
                if(!folder.exists() && !folder.mkdirs()) throw new java.io.IOException("No Downloads folder.");
                File target = new File(folder, name);
                for(int attempt = 1; target.exists() && attempt < 100; attempt++){
                    int dot = name.lastIndexOf('.');
                    String stem = dot > 0 ? name.substring(0, dot) : name;
                    String suffix = dot > 0 ? name.substring(dot) : "";
                    target = new File(folder, stem + "-" + attempt + suffix);
                }
                try(FileOutputStream out = new FileOutputStream(target)){ out.write(bytes); }
            }
            Toast.makeText(this,"Saved to Downloads: " + name,Toast.LENGTH_LONG).show();
        }catch(Exception error){
            Toast.makeText(this,"Could not save the file: " + error.getMessage(),Toast.LENGTH_LONG).show();
        }
    }

    /** A safe file name: never trust one supplied by the page. */
    private String fileNameFrom(String disposition, String header){
        String name = "linguafusion-export";
        if(disposition != null){
            java.util.regex.Matcher matcher =
                java.util.regex.Pattern.compile("filename=\"?([^\";]+)").matcher(disposition);
            if(matcher.find()) name = matcher.group(1);
        }
        name = name.replaceAll("[^A-Za-z0-9._-]", "_");
        if(name.isEmpty() || name.startsWith(".")) name = "linguafusion-export";
        if(!name.contains(".")){
            String extension = header.contains("csv") ? ".csv" : header.contains("markdown") ? ".md" : ".txt";
            name = name + extension;
        }
        return name.length() > 80 ? name.substring(name.length() - 80) : name;
    }

    private boolean isCloudOrigin(Uri target){
        Uri base=Uri.parse(CLOUD_BASE);
        return Objects.equals(base.getScheme(),target.getScheme())
            && Objects.equals(base.getHost(),target.getHost())
            && effectivePort(base)==effectivePort(target);
    }

    // A page may REQUEST the dialog, but recording only starts on a native tap.
    // No native settings, credentials or arbitrary files are exposed to the page.
    private void showCloudRecorder(WebView owner,String requestId){
        if(cloudRecorderDialog!=null || requestId==null || !requestId.matches("[a-zA-Z0-9-]{1,80}"))return;
        AlertDialog dialog=new AlertDialog.Builder(this)
            .setTitle("Record speech")
            .setMessage("Up to 60 seconds. Stop and send uploads audio for paid cloud transcription. Cancel discards it.")
            .setPositiveButton("Start",null).setNegativeButton("Cancel",null).create();
        cloudRecorderDialog=dialog;
        final boolean[] delivered={false};
        Runnable finish=() -> {
            if(cloudRecorderDialog!=dialog)return;
            if(cloudRecordingTimeout!=null)recordingHandler.removeCallbacks(cloudRecordingTimeout);
            String result=stopNativeAudioRecording();
            delivered[0]=true;
            sendCloudRecording(owner,requestId,result.startsWith("ERROR:")?"error":"audio",result);
            dialog.dismiss();
        };
        dialog.setOnDismissListener(ignored -> {
            if(cloudRecordingTimeout!=null)recordingHandler.removeCallbacks(cloudRecordingTimeout);
            cloudRecordingTimeout=null;
            cancelNativeAudioRecording();
            cloudRecorderDialog=null;
            if(!delivered[0])sendCloudRecording(owner,requestId,"cancel","");
        });
        dialog.setOnShowListener(ignored -> dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener(button -> {
            if(nativeAudioRecording){finish.run();return;}
            String result=startNativeAudioRecording();
            if("PERMISSION_REQUIRED".equals(result)){
                dialog.setMessage("Allow microphone access, then tap Start again.");
            }else if(!"OK".equals(result)){
                dialog.setMessage(result+" You can also use the cloud website in Chrome.");
            }else{
                dialog.setMessage("Recording. Stop and send when ready; automatically stops at 60 seconds.");
                dialog.getButton(AlertDialog.BUTTON_POSITIVE).setText("Stop and send");
                cloudRecordingTimeout=finish;
                recordingHandler.postDelayed(finish,60000);
            }
        }));
        dialog.show();
    }

    private void sendCloudRecording(WebView owner,String id,String kind,String data){
        if(owner!=webView || !isCloudOrigin(Uri.parse(owner.getUrl()==null?"":owner.getUrl())))return;
        owner.evaluateJavascript("window.dispatchEvent(new CustomEvent('lf-native-recording',{detail:{id:"
            +jsQuote(id)+",kind:"+jsQuote(kind)+",data:"+jsQuote(data)+"}}));",null);
    }

    private void showCloudUnavailable(String detail){
        releaseWebView();
        applySystemBarTheme(false);
        ScrollView scroll=new ScrollView(this); scroll.setFillViewport(true); scroll.setBackgroundColor(Color.rgb(246,248,252));
        LinearLayout root=new LinearLayout(this); root.setOrientation(LinearLayout.VERTICAL); root.setPadding(dp(24),dp(54),dp(24),dp(32)); scroll.addView(root);
        TextView title=text("LinguaFusion Cloud is unreachable",24,true); root.addView(title);
        TextView reason=text(detail,14,false); reason.setTextColor(Color.rgb(102,112,133)); margin(reason,12); root.addView(reason);
        TextView hint=text("Check this phone's internet connection. If it keeps failing, the owner may have stopped the service.",13,false); hint.setTextColor(Color.rgb(102,112,133)); margin(hint,10); root.addView(hint);
        Button retry=new Button(this); retry.setText("Try again"); retry.setAllCaps(false); retry.setTextSize(15); retry.setTextColor(Color.WHITE); retry.setBackground(background(Color.rgb(11,87,208),Color.TRANSPARENT,10)); margin(retry,22); root.addView(retry,new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT,dp(50)));
        retry.setOnClickListener(view -> showCloudApp());
        Button usePc=new Button(this); usePc.setText("Connect to a PC instead"); usePc.setAllCaps(false); usePc.setTextSize(15); usePc.setTextColor(Color.rgb(11,87,208)); usePc.setBackground(background(Color.WHITE,Color.rgb(215,222,232),10)); margin(usePc,12); root.addView(usePc,new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT,dp(50)));
        usePc.setOnClickListener(view -> {preferences.edit().remove("mode").apply();showConnectionScreen();});
        setInsetContentView(scroll);
    }
    private void releaseWebView(){
        if(cloudRecorderDialog!=null)cloudRecorderDialog.dismiss();
        if(pendingAudioRequest!=null){pendingAudioRequest.deny();pendingAudioRequest=null;}
        cancelNativeAudioRecording();
        if(webView==null)return;
        webView.stopLoading();webView.removeJavascriptInterface("LinguaFusionNative");webView.removeJavascriptInterface("LinguaFusionOffline");webView.setWebChromeClient(null);webView.setWebViewClient(null);webView.destroy();webView=null;
    }
    private String jsQuote(String value){
        return JSONObject.quote(value == null ? "" : value);
    }
    private boolean requestsAudioOnly(PermissionRequest request){
        String[] resources=request.getResources();
        return resources.length==1 && PermissionRequest.RESOURCE_AUDIO_CAPTURE.equals(resources[0]);
    }
    private boolean isTrustedOrigin(Uri origin){
        Uri expected=Uri.parse(preferences.getString("server",""));
        return Objects.equals(expected.getScheme(),origin.getScheme())
            && Objects.equals(expected.getHost(),origin.getHost())
            && effectivePort(expected)==effectivePort(origin);
    }
    private int effectivePort(Uri uri){
        if(uri.getPort()!=-1)return uri.getPort();
        return "https".equalsIgnoreCase(uri.getScheme())?443:80;
    }

    public final class NativeBridge {
        @JavascriptInterface public void saveConnection(String server,String key){preferences.edit().putString("server",server).putString("key",key).apply();}
        @JavascriptInterface public void resetConnection(){preferences.edit().clear().apply();runOnUiThread(MainActivity.this::showConnectionScreen);}
        @JavascriptInterface public boolean supportsAudioRecording(){return true;}
        @JavascriptInterface public void setSystemBarTheme(boolean dark){runOnUiThread(() -> applySystemBarTheme(dark));}
        @JavascriptInterface public String startAudioRecording(){return startNativeAudioRecording();}
        @JavascriptInterface public String stopAudioRecording(){return stopNativeAudioRecording();}
        @JavascriptInterface public void cancelAudioRecording(){cancelNativeAudioRecording();}
    }

    private String startNativeAudioRecording(){
        if(checkSelfPermission(Manifest.permission.RECORD_AUDIO)!=PackageManager.PERMISSION_GRANTED){
            runOnUiThread(() -> requestPermissions(new String[]{Manifest.permission.RECORD_AUDIO},AUDIO_PERMISSION));
            return "PERMISSION_REQUIRED";
        }
        synchronized(nativeAudioLock){
            if(nativeAudioRecording)return "ERROR: Recording is already active.";
            try{
                int minimum=AudioRecord.getMinBufferSize(NATIVE_SAMPLE_RATE,AudioFormat.CHANNEL_IN_MONO,AudioFormat.ENCODING_PCM_16BIT);
                if(minimum<=0)throw new java.io.IOException("The phone did not provide a microphone buffer.");
                int bufferSize=Math.max(minimum*2,4096);
                AudioRecord recorder=new AudioRecord(MediaRecorder.AudioSource.VOICE_RECOGNITION,NATIVE_SAMPLE_RATE,AudioFormat.CHANNEL_IN_MONO,AudioFormat.ENCODING_PCM_16BIT,bufferSize);
                if(recorder.getState()!=AudioRecord.STATE_INITIALIZED){recorder.release();throw new java.io.IOException("The phone microphone could not be initialized.");}
                File pcmFile=new File(getCacheDir(),"linguafusion-recording.pcm");
                nativeAudioRecord=recorder;nativeAudioFile=pcmFile;nativeAudioRecording=true;
                recorder.startRecording();
                nativeAudioThread=new Thread(() -> writeNativePcm(recorder,pcmFile,bufferSize),"LinguaFusionAudio");
                nativeAudioThread.start();
                return "OK";
            }catch(Exception error){
                if(nativeAudioRecord!=null){try{nativeAudioRecord.release();}catch(Exception ignored){}}
                nativeAudioRecording=false;nativeAudioRecord=null;nativeAudioThread=null;nativeAudioFile=null;
                return "ERROR: "+error.getMessage();
            }
        }
    }

    private void writeNativePcm(AudioRecord recorder,File outputFile,int bufferSize){
        byte[] buffer=new byte[bufferSize];
        // Cloud recordings are capped at 60s by the dialog. Offline ones need
        // their own cap: transcription turns every sample into a 4-byte float,
        // so an unbounded recording becomes an unbounded allocation.
        int remaining=cloudRecorderDialog!=null?NATIVE_SAMPLE_RATE*2*60
            :("offline".equals(preferences.getString("mode",""))?NATIVE_SAMPLE_RATE*2*OFFLINE_RECORDING_SECONDS:Integer.MAX_VALUE);
        try(FileOutputStream output=new FileOutputStream(outputFile,false)){
            while(nativeAudioRecording && remaining>0){
                int count=recorder.read(buffer,0,Math.min(buffer.length,remaining));
                if(count>0){output.write(buffer,0,count);remaining-=count;}
                else if(count<0)break;
            }
        }catch(Exception ignored){}
    }

    /** Stops the recorder and returns the raw 16 kHz mono PCM it captured.
     *  Offline transcription wants exactly this, so the audio can go straight
     *  into Whisper without a WAV header, a base64 round trip through
     *  JavaScript, or ever leaving Java. Returns null if nothing was recorded. */
    private byte[] stopNativeAudioRecordingToPcm(){
        File pcmFile;AudioRecord recorder;Thread thread;
        synchronized(nativeAudioLock){
            if(!nativeAudioRecording||nativeAudioRecord==null)return null;
            nativeAudioRecording=false;recorder=nativeAudioRecord;thread=nativeAudioThread;pcmFile=nativeAudioFile;
            nativeAudioRecord=null;nativeAudioThread=null;nativeAudioFile=null;
        }
        try{recorder.stop();}catch(Exception ignored){}
        try{if(thread!=null)thread.join(2500);}catch(InterruptedException error){Thread.currentThread().interrupt();}
        recorder.release();
        try{
            byte[] pcm=Files.readAllBytes(pcmFile.toPath());
            pcmFile.delete();
            return pcm;
        }catch(Exception error){
            if(pcmFile!=null)pcmFile.delete();
            return null;
        }
    }

    private String stopNativeAudioRecording(){
        boolean active;
        synchronized(nativeAudioLock){active=nativeAudioRecording&&nativeAudioRecord!=null;}
        if(!active)return "ERROR: No recording is active.";
        byte[] pcm=stopNativeAudioRecordingToPcm();
        if(pcm==null)return "ERROR: Could not prepare the recording.";
        if(pcm.length<2)return "ERROR: No speech was recorded.";
        try{
            return Base64.encodeToString(wavFromPcm(pcm),Base64.NO_WRAP);
        }catch(Exception error){return "ERROR: Could not prepare the recording: "+error.getMessage();}
    }

    private void cancelNativeAudioRecording(){
        AudioRecord recorder;Thread thread;File pcmFile;
        synchronized(nativeAudioLock){
            nativeAudioRecording=false;recorder=nativeAudioRecord;thread=nativeAudioThread;pcmFile=nativeAudioFile;
            nativeAudioRecord=null;nativeAudioThread=null;nativeAudioFile=null;
        }
        if(recorder!=null){try{recorder.stop();}catch(Exception ignored){}recorder.release();}
        try{if(thread!=null)thread.join(600);}catch(InterruptedException error){Thread.currentThread().interrupt();}
        if(pcmFile!=null)pcmFile.delete();
    }

    private byte[] wavFromPcm(byte[] pcm)throws Exception{
        ByteArrayOutputStream wav=new ByteArrayOutputStream(pcm.length+44);
        writeAscii(wav,"RIFF");writeLittleEndian(wav,36+pcm.length,4);writeAscii(wav,"WAVE");
        writeAscii(wav,"fmt ");writeLittleEndian(wav,16,4);writeLittleEndian(wav,1,2);writeLittleEndian(wav,1,2);
        writeLittleEndian(wav,NATIVE_SAMPLE_RATE,4);writeLittleEndian(wav,NATIVE_SAMPLE_RATE*2,4);writeLittleEndian(wav,2,2);writeLittleEndian(wav,16,2);
        writeAscii(wav,"data");writeLittleEndian(wav,pcm.length,4);wav.write(pcm);return wav.toByteArray();
    }
    private void writeAscii(ByteArrayOutputStream output,String value)throws Exception{output.write(value.getBytes(StandardCharsets.US_ASCII));}
    private void writeLittleEndian(ByteArrayOutputStream output,int value,int bytes){for(int index=0;index<bytes;index++)output.write((value>>(8*index))&0xff);}

    @Override protected void onActivityResult(int requestCode,int resultCode,Intent data){
        super.onActivityResult(requestCode,resultCode,data);if(requestCode==FILE_REQUEST&&fileCallback!=null){fileCallback.onReceiveValue(WebChromeClient.FileChooserParams.parseResult(resultCode,data));fileCallback=null;}
    }
    @Override public void onRequestPermissionsResult(int requestCode,String[] permissions,int[] grantResults){
        super.onRequestPermissionsResult(requestCode,permissions,grantResults);
        if(requestCode!=AUDIO_PERMISSION)return;
        boolean granted=grantResults.length>0&&grantResults[0]==PackageManager.PERMISSION_GRANTED;
        if(pendingAudioRequest!=null){
            if(granted){
                pendingAudioRequest.grant(new String[]{PermissionRequest.RESOURCE_AUDIO_CAPTURE});
            }else pendingAudioRequest.deny();
            pendingAudioRequest=null;
        }else if(webView!=null){
            String callback="if(window.LFNativeAudioPermissionResult){window.LFNativeAudioPermissionResult("+(granted?"true":"false")+");}";
            webView.post(() -> {if(webView!=null)webView.evaluateJavascript(callback,null);});
        }
    }
    @Override public void onBackPressed(){if(webView!=null&&webView.canGoBack())webView.goBack();else super.onBackPressed();}
    @Override protected void onPause(){
        if(cloudRecorderDialog!=null && nativeAudioRecording)cloudRecorderDialog.dismiss();
        super.onPause();
    }
    @Override protected void onDestroy(){releaseWebView();executor.shutdownNow();super.onDestroy();}
}
