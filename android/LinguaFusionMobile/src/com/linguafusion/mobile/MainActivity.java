package com.linguafusion.mobile;

import android.Manifest;
import android.app.Activity;
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
    private final Object nativeAudioLock = new Object();
    private volatile boolean nativeAudioRecording;
    private AudioRecord nativeAudioRecord;
    private Thread nativeAudioThread;
    private File nativeAudioFile;
    private static final int NATIVE_SAMPLE_RATE = 16000;

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        applySystemBarTheme(false);
        preferences = getSharedPreferences("linguafusion", MODE_PRIVATE);
        if (handlePairingIntent(getIntent())) return;
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
        webView=new WebView(this); webView.setBackgroundColor(Color.rgb(246,248,252));
        WebSettings settings=webView.getSettings(); settings.setJavaScriptEnabled(true);settings.setDomStorageEnabled(true);settings.setMediaPlaybackRequiresUserGesture(false);settings.setAllowFileAccess(true);settings.setAllowContentAccess(true);
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
        webView.setWebChromeClient(new WebChromeClient(){
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
        webView.loadUrl(server+"/mobile/"); setInsetContentView(webView);
    }
    private void releaseWebView(){
        cancelNativeAudioRecording();
        if(webView==null)return;
        webView.stopLoading();webView.removeJavascriptInterface("LinguaFusionNative");webView.setWebChromeClient(null);webView.setWebViewClient(null);webView.destroy();webView=null;
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
                nativeAudioRecording=false;nativeAudioRecord=null;nativeAudioThread=null;nativeAudioFile=null;
                return "ERROR: "+error.getMessage();
            }
        }
    }

    private void writeNativePcm(AudioRecord recorder,File outputFile,int bufferSize){
        byte[] buffer=new byte[bufferSize];
        try(FileOutputStream output=new FileOutputStream(outputFile,false)){
            while(nativeAudioRecording){
                int count=recorder.read(buffer,0,buffer.length);
                if(count>0)output.write(buffer,0,count);
                else if(count<0)break;
            }
        }catch(Exception ignored){}
    }

    private String stopNativeAudioRecording(){
        File pcmFile;AudioRecord recorder;Thread thread;
        synchronized(nativeAudioLock){
            if(!nativeAudioRecording||nativeAudioRecord==null)return "ERROR: No recording is active.";
            nativeAudioRecording=false;recorder=nativeAudioRecord;thread=nativeAudioThread;pcmFile=nativeAudioFile;
            nativeAudioRecord=null;nativeAudioThread=null;nativeAudioFile=null;
        }
        try{recorder.stop();}catch(Exception ignored){}
        try{if(thread!=null)thread.join(2500);}catch(InterruptedException error){Thread.currentThread().interrupt();}
        recorder.release();
        try{
            byte[] pcm=Files.readAllBytes(pcmFile.toPath());
            pcmFile.delete();
            if(pcm.length<2)return "ERROR: No speech was recorded.";
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
    @Override protected void onDestroy(){releaseWebView();executor.shutdownNow();super.onDestroy();}
}
