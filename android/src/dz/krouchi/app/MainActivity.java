package dz.krouchi.app;

import android.app.Activity;
import android.content.ClipData;
import android.content.ContentValues;
import android.content.Intent;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Environment;
import android.provider.MediaStore;
import android.util.Base64;
import android.webkit.JavascriptInterface;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceResponse;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Toast;

import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.DatagramPacket;
import java.net.DatagramSocket;
import java.net.HttpURLConnection;
import java.net.InetAddress;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.Iterator;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/**
 * Krouchi_DZ — رفيق الهاتف لبرنامج Krouchi_DZ المكتبي (شيفرة أصلية).
 *
 * نشاط واحد يستضيف واجهة HTML/JS من أصول التطبيق عبر نطاق وهمي
 * محلي (https://krouchi.local/)، ويقدّم للواجهة جسر HTTP أصيلاً
 * (HttpURLConnection) حتى تعمل طلبات اكتشاف النماذج والمحادثة
 * بمفتاح المستخدم دون قيود CORS الخاصة بالويب فيو.
 *
 * النسخة 2.0: إدخال API + اكتشاف نماذج + محادثة محلية، ووضع
 * مرافق للحاسوب: الاتصال بخادم Krouchi_DZ المكتبي على الشبكة
 * المحلية (http://<pc>:8765 + ترويسة X-Krouchi-Token) للمحادثة
 * عبر بوتات الحاسوب والموافقة على طلبات تنفيذه أو رفضها.
 * لا أدوات ملفات ولا أوامر على الهاتف نفسه. المفاتيح والبيانات
 * في تخزين التطبيق الخاص (DOM Storage للويب فيو).
 */
public class MainActivity extends Activity {

    private static final String ASSET_HOST = "https://krouchi.local/";
    private static final String HOME_URL = ASSET_HOST + "index.html";
    private static final int FILE_CHOOSER_REQUEST_CODE = 1001;

    private WebView webView;
    private ValueCallback<Uri[]> filePathCallback;
    private final ExecutorService httpPool = Executors.newCachedThreadPool();

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        webView = new WebView(this);
        setContentView(webView);

        WebSettings settings = webView.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        // شاشة الحاسوب ووسائطه تُحمَّل من حاسوب المستخدم نفسه عبر http
        // على الشبكة المحلية/Tailscale — بلا هذا الوضع يحجب WebView
        // ذلك المحتوى الصافي كمختلط من أصل الواجهة https الوهمي
        settings.setMixedContentMode(WebSettings.MIXED_CONTENT_ALWAYS_ALLOW);
        settings.setDatabaseEnabled(true);

        webView.setWebViewClient(new WebViewClient() {
            @Override
            public WebResourceResponse shouldInterceptRequest(WebView view,
                                                              WebResourceRequest request) {
                String url = request.getUrl().toString();
                if (url.startsWith(ASSET_HOST)) {
                    String name = url.substring(ASSET_HOST.length());
                    int q = name.indexOf('?');
                    if (q >= 0) name = name.substring(0, q);
                    if (name.equals("index.html") || name.equals("app.js")) {
                        try {
                            InputStream is = getAssets().open(name);
                            String mime = name.endsWith(".js")
                                    ? "application/javascript" : "text/html";
                            return new WebResourceResponse(mime, "UTF-8", is);
                        } catch (IOException e) {
                            return null;
                        }
                    }
                    if (name.startsWith("avatars/bot_") && name.endsWith(".png")
                            && !name.contains("..")
                            && name.indexOf('/', 8) == -1) {
                        String digits = name.substring("avatars/bot_".length(),
                                name.length() - ".png".length());
                        if (digits.length() >= 1 && digits.length() <= 2) {
                            boolean allDigits = true;
                            for (int i = 0; i < digits.length(); i++) {
                                if (!Character.isDigit(digits.charAt(i))) {
                                    allDigits = false;
                                    break;
                                }
                            }
                            if (allDigits) {
                                try {
                                    InputStream is = getAssets().open(name);
                                    return new WebResourceResponse("image/png", null, is);
                                } catch (IOException e) {
                                    return null;
                                }
                            }
                        }
                    }
                }
                return null;
            }
        });

        webView.setWebChromeClient(new WebChromeClient() {
            @Override
            public boolean onShowFileChooser(WebView webView,
                                             ValueCallback<Uri[]> callback,
                                             FileChooserParams fileChooserParams) {
                if (filePathCallback != null) {
                    filePathCallback.onReceiveValue(null);
                    filePathCallback = null;
                }
                filePathCallback = callback;
                Intent intent = new Intent(Intent.ACTION_GET_CONTENT);
                intent.addCategory(Intent.CATEGORY_OPENABLE);
                intent.setType("*/*");
                try {
                    startActivityForResult(intent, FILE_CHOOSER_REQUEST_CODE);
                } catch (Exception e) {
                    if (filePathCallback != null) {
                        filePathCallback.onReceiveValue(null);
                        filePathCallback = null;
                    }
                    return false;
                }
                return true;
            }
        });

        webView.addJavascriptInterface(new Bridge(), "KrouchiBridge");
        webView.loadUrl(HOME_URL);
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode == FILE_CHOOSER_REQUEST_CODE) {
            if (filePathCallback == null) {
                return;
            }
            Uri[] results = null;
            if (resultCode == RESULT_OK && data != null) {
                ClipData clipData = data.getClipData();
                if (clipData != null) {
                    int count = clipData.getItemCount();
                    if (count > 0) {
                        results = new Uri[count];
                        for (int i = 0; i < count; i++) {
                            results[i] = clipData.getItemAt(i).getUri();
                        }
                    }
                } else if (data.getData() != null) {
                    results = new Uri[]{data.getData()};
                }
            }
            ValueCallback<Uri[]> callback = filePathCallback;
            filePathCallback = null;
            callback.onReceiveValue(results);
        }
    }

    @Override
    public void onBackPressed() {
        if (webView != null && webView.canGoBack()) {
            webView.goBack();
        } else {
            super.onBackPressed();
        }
    }

    @Override
    protected void onDestroy() {
        httpPool.shutdownNow();
        super.onDestroy();
    }

    /**
     * جسر JavaScript: طلب HTTP أصيل من الواجهة.
     *
     * http(reqId, method, url, headersJson, body[, readTimeoutMs])
     *   headersJson: كائن JSON {name: value} أو "" لغياب الترويسات.
     *   body: نص الطلب أو "" لطلب بلا جسم.
     *   readTimeoutMs (اختياري): مهلة قراءة بالميلي ثانية (افتراضي 90s،
     *   تُقصّ بين 15s و300s) — لمحادثة الحاسوب المنتظِرة موافقة.
     * النتيجة تصل إلى window.__krouchiHttpDone(reqId, status, bodyB64, error)
     * حيث status=0 عند فشل شبكي (error يصف السبب)، و bodyB64 هو جسم
     * الردّ مشفّراً بـ Base64 (قد يكون "" عند الخطأ الشبكي).
     */
    public class Bridge {

        @JavascriptInterface
        public void toast(final String msg) {
            runOnUiThread(new Runnable() {
                @Override
                public void run() {
                    Toast.makeText(MainActivity.this, msg, Toast.LENGTH_LONG).show();
                }
            });
        }

        @JavascriptInterface
        public String saveFile(String name, String base64) {
            try {
                String safeName = sanitizeFileName(name);
                byte[] bytes = Base64.decode(base64, Base64.DEFAULT);
                if (Build.VERSION.SDK_INT >= 29) {
                    ContentValues values = new ContentValues();
                    values.put(MediaStore.Downloads.DISPLAY_NAME, safeName);
                    values.put(MediaStore.Downloads.MIME_TYPE, "application/octet-stream");
                    values.put(MediaStore.Downloads.RELATIVE_PATH, Environment.DIRECTORY_DOWNLOADS);
                    values.put(MediaStore.Downloads.IS_PENDING, 1);
                    Uri uri = getContentResolver().insert(
                            MediaStore.Downloads.EXTERNAL_CONTENT_URI, values);
                    if (uri == null) {
                        return "error: insert failed";
                    }
                    OutputStream os = null;
                    try {
                        os = getContentResolver().openOutputStream(uri);
                        if (os == null) {
                            return "error: openOutputStream failed";
                        }
                        os.write(bytes);
                        os.flush();
                    } finally {
                        if (os != null) {
                            try { os.close(); } catch (IOException ignored) {}
                        }
                    }
                    ContentValues done = new ContentValues();
                    done.put(MediaStore.Downloads.IS_PENDING, 0);
                    getContentResolver().update(uri, done, null, null);
                } else {
                    File dir = Environment.getExternalStoragePublicDirectory(
                            Environment.DIRECTORY_DOWNLOADS);
                    if (dir != null && !dir.exists()) {
                        //noinspection ResultOfMethodCallIgnored
                        dir.mkdirs();
                    }
                    File outFile = new File(dir, safeName);
                    FileOutputStream fos = null;
                    try {
                        fos = new FileOutputStream(outFile);
                        fos.write(bytes);
                        fos.flush();
                    } finally {
                        if (fos != null) {
                            try { fos.close(); } catch (IOException ignored) {}
                        }
                    }
                }
                runOnUiThread(new Runnable() {
                    @Override
                    public void run() {
                        Toast.makeText(MainActivity.this, "تم الحفظ في التنزيلات",
                                Toast.LENGTH_LONG).show();
                    }
                });
                return "ok";
            } catch (Exception e) {
                String msg = e.getMessage();
                return "error: " + (msg != null ? msg : e.getClass().getSimpleName());
            }
        }

        private String sanitizeFileName(String name) {
            if (name == null) {
                return "download";
            }
            String n = name.trim();
            // Take basename only: strip any directory components.
            int slash = Math.max(n.lastIndexOf('/'), n.lastIndexOf('\\'));
            if (slash >= 0 && slash + 1 < n.length()) {
                n = n.substring(slash + 1);
            } else if (slash >= 0) {
                n = "";
            }
            n = n.trim();
            if (n.isEmpty() || ".".equals(n) || "..".equals(n)) {
                return "download";
            }
            return n;
        }

        @JavascriptInterface
        public void http(final String reqId, final String method, final String url,
                         final String headersJson, final String body) {
            doHttp(reqId, method, url, headersJson, body, 90000);
        }

        /**
         * إيقاظ الحاسوب عبر الشبكة (Wake-on-LAN): تُبنى الحزمة السحرية
         * (102 بايت: 6 بايتات 0xFF ثم عنوان MAC مكرراً 16 مرة) وتُبثّ
         * عبر UDP إلى 255.255.255.255 على المنفذين 9 و7، في خيط خلفي.
         * يقبل العنوان بصيغ AA:BB:CC:DD:EE:FF أو AA-BB-CC-DD-EE-FF
         * أو 12 رقماً سداسياً متصلاً؛ غير الصالح يُرفض بتنبيه.
         */
        @JavascriptInterface
        public void wol(final String mac) {
            final byte[] macBytes = parseMac(mac);
            if (macBytes == null) {
                toast("Invalid MAC address");
                return;
            }
            final byte[] packet = new byte[102];
            for (int i = 0; i < 6; i++) packet[i] = (byte) 0xFF;
            for (int i = 0; i < 16; i++) {
                System.arraycopy(macBytes, 0, packet, 6 + i * 6, 6);
            }
            new Thread(new Runnable() {
                @Override
                public void run() {
                    DatagramSocket socket = null;
                    try {
                        socket = new DatagramSocket();
                        socket.setBroadcast(true);
                        InetAddress broadcast =
                                InetAddress.getByName("255.255.255.255");
                        socket.send(new DatagramPacket(
                                packet, packet.length, broadcast, 9));
                        socket.send(new DatagramPacket(
                                packet, packet.length, broadcast, 7));
                        toast("Wake packet sent");
                    } catch (Exception e) {
                        toast("Wake failed: " + e.getClass().getSimpleName());
                    } finally {
                        if (socket != null) socket.close();
                    }
                }
            }).start();
        }

        /* تحليل عنوان MAC إلى 6 بايتات، أو null عند أي صيغة غير صالحة */
        private byte[] parseMac(String mac) {
            if (mac == null) return null;
            String hex = mac.trim().replace(":", "").replace("-", "");
            if (hex.length() != 12) return null;
            byte[] out = new byte[6];
            for (int i = 0; i < 6; i++) {
                try {
                    out[i] = (byte) Integer.parseInt(
                            hex.substring(i * 2, i * 2 + 2), 16);
                } catch (NumberFormatException e) {
                    return null;
                }
            }
            return out;
        }

        /**
         * صيغة بمهلة قراءة ممتدة: محادثة الحاسوب قد تنتظر موافقة
         * على جانب الحاسوب حتى ~120 ثانية، فنسمح حتى 300 ثانية.
         */
        @JavascriptInterface
        public void http(final String reqId, final String method, final String url,
                         final String headersJson, final String body,
                         final int readTimeoutMs) {
            int rt = readTimeoutMs;
            if (rt < 15000) rt = 15000;
            if (rt > 300000) rt = 300000;
            doHttp(reqId, method, url, headersJson, body, rt);
        }

        private void doHttp(final String reqId, final String method, final String url,
                            final String headersJson, final String body,
                            final int readTimeoutMs) {
            httpPool.execute(new Runnable() {
                @Override
                public void run() {
                    int status = 0;
                    String responseText = "";
                    String error = "";
                    HttpURLConnection conn = null;
                    try {
                        conn = (HttpURLConnection) new URL(url).openConnection();
                        conn.setRequestMethod(method == null ? "GET" : method);
                        conn.setConnectTimeout(20000);
                        conn.setReadTimeout(readTimeoutMs);
                        if (headersJson != null && !headersJson.trim().isEmpty()) {
                            JSONObject headers = new JSONObject(headersJson);
                            Iterator<String> keys = headers.keys();
                            while (keys.hasNext()) {
                                String k = keys.next();
                                conn.setRequestProperty(k, headers.optString(k));
                            }
                        }
                        if (body != null && !body.isEmpty()) {
                            byte[] payload = body.getBytes(StandardCharsets.UTF_8);
                            conn.setDoOutput(true);
                            conn.setRequestProperty("Content-Length",
                                    String.valueOf(payload.length));
                            OutputStream os = conn.getOutputStream();
                            os.write(payload);
                            os.flush();
                            os.close();
                        }
                        status = conn.getResponseCode();
                        InputStream is = status >= 400
                                ? conn.getErrorStream() : conn.getInputStream();
                        if (is != null) {
                            responseText = readAll(is);
                        }
                    } catch (Exception e) {
                        status = 0;
                        error = e.getClass().getSimpleName()
                                + (e.getMessage() != null ? ": " + e.getMessage() : "");
                    } finally {
                        if (conn != null) conn.disconnect();
                    }
                    deliver(reqId, status, responseText, error);
                }
            });
        }

        private String readAll(InputStream is) throws IOException {
            BufferedReader reader = new BufferedReader(
                    new InputStreamReader(is, StandardCharsets.UTF_8));
            StringBuilder sb = new StringBuilder();
            char[] buf = new char[4096];
            int n;
            while ((n = reader.read(buf)) > 0) {
                sb.append(buf, 0, n);
            }
            reader.close();
            return sb.toString();
        }

        private void deliver(final String reqId, final int status,
                             final String responseText, final String error) {
            final String bodyB64 = Base64.encodeToString(
                    responseText.getBytes(StandardCharsets.UTF_8), Base64.NO_WRAP);
            final String js = "window.__krouchiHttpDone && window.__krouchiHttpDone("
                    + JSONObject.quote(reqId) + ", " + status + ", "
                    + JSONObject.quote(bodyB64) + ", "
                    + JSONObject.quote(error) + ");";
            runOnUiThread(new Runnable() {
                @Override
                public void run() {
                    if (webView != null) webView.evaluateJavascript(js, null);
                }
            });
        }
    }
}
