package com.yyyan44.daka;

import android.app.Activity;
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
import android.webkit.WebSettings;
import android.webkit.WebView;

import java.io.File;
import java.io.FileOutputStream;
import java.io.OutputStream;

/**
 * 一键打卡 · 安卓壳。
 *
 * 网页负责界面和逻辑（都在 assets 里），这个类只做三件网页办不到的事：
 *   1. 接管 <input type="file">，调起系统相册多选图
 *   2. 把网页生成的 docx（base64）写进「下载/一键打卡/」，不需要任何存储权限
 *   3. 把刚生成的文档用系统分享发出去（微信、QQ、邮件…）
 *
 * 声明里没有 INTERNET 权限，所以这个 App 在系统层面无法联网。
 */
public class MainActivity extends Activity {

    private static final String DOCX_MIME =
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document";
    private static final int REQ_FILE = 1001;

    private WebView web;
    private ValueCallback<Uri[]> fileCallback;
    private Uri lastUri;            // 刚写出去的文档（分享用）
    private String lastWhere = "";  // 给用户看的保存位置

    /** 暴露给网页的接口：window.Daka.xxx(...) */
    public class Bridge {
        @JavascriptInterface
        public String saveDocx(String base64, String filename) {
            return save(base64, filename, false);
        }

        @JavascriptInterface
        public String saveAndShare(String base64, String filename) {
            return save(base64, filename, true);
        }

        @JavascriptInterface
        public String shareLast() {
            return share();
        }

        @JavascriptInterface
        public String openLast() {
            return open();
        }

        @JavascriptInterface
        public String version() {
            return "1.0";
        }
    }

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        web = new WebView(this);
        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);     // 设置项存 localStorage
        s.setDatabaseEnabled(true);       // 选中的图存 IndexedDB（重启后还在）
        s.setAllowFileAccess(true);       // 读 assets 里的 js/html

        web.addJavascriptInterface(new Bridge(), "Daka");

        web.setWebChromeClient(new WebChromeClient() {
            @Override
            public boolean onShowFileChooser(WebView v, ValueCallback<Uri[]> cb,
                                             FileChooserParams params) {
                if (fileCallback != null) {
                    fileCallback.onReceiveValue(null);
                }
                fileCallback = cb;
                Intent i = new Intent(Intent.ACTION_GET_CONTENT);
                i.addCategory(Intent.CATEGORY_OPENABLE);
                i.setType("image/*");
                i.putExtra(Intent.EXTRA_ALLOW_MULTIPLE, true);
                try {
                    startActivityForResult(Intent.createChooser(i, "选择截图"), REQ_FILE);
                    return true;
                } catch (Exception e) {
                    fileCallback = null;
                    return false;
                }
            }
        });

        web.loadUrl("file:///android_asset/index.html");
        setContentView(web);
    }

    // ───────── 写文件 ─────────
    private String save(String base64, String filename, boolean shareNow) {
        try {
            byte[] data = Base64.decode(base64, Base64.DEFAULT);
            String name = (filename == null || filename.trim().isEmpty())
                    ? "打卡表.docx" : filename.trim();

            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                // 先删掉同名的旧文件，免得 MediaStore 自动改名成「xxx (1).docx」
                String rel = Environment.DIRECTORY_DOWNLOADS + "/一键打卡";
                for (String r : new String[]{rel + "/", rel}) {
                    try {
                        getContentResolver().delete(MediaStore.Downloads.EXTERNAL_CONTENT_URI,
                                MediaStore.MediaColumns.DISPLAY_NAME + "=? AND "
                                        + MediaStore.MediaColumns.RELATIVE_PATH + "=?",
                                new String[]{name, r});
                    } catch (Exception ignored) {
                    }
                }

                ContentValues v = new ContentValues();
                v.put(MediaStore.MediaColumns.DISPLAY_NAME, name);
                v.put(MediaStore.MediaColumns.MIME_TYPE, DOCX_MIME);
                v.put(MediaStore.MediaColumns.RELATIVE_PATH,
                        Environment.DIRECTORY_DOWNLOADS + "/一键打卡");
                Uri uri = getContentResolver().insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, v);
                if (uri == null) {
                    return "ERR:创建文件失败（下载目录不可写）";
                }
                OutputStream os = getContentResolver().openOutputStream(uri);
                if (os == null) {
                    return "ERR:打开输出流出错";
                }
                os.write(data);
                os.flush();
                os.close();
                lastUri = uri;
                lastWhere = "下载/一键打卡/" + name;
            } else {
                File dir = new File(getExternalFilesDir(null), "一键打卡");
                if (!dir.exists() && !dir.mkdirs()) {
                    return "ERR:无法创建目录";
                }
                File f = new File(dir, name);
                FileOutputStream fo = new FileOutputStream(f);
                fo.write(data);
                fo.flush();
                fo.close();
                lastUri = Uri.fromFile(f);
                lastWhere = f.getAbsolutePath();
            }
            return shareNow ? share() : ("OK:" + lastWhere);
        } catch (Exception e) {
            return "ERR:" + e;
        }
    }

    private String share() {
        if (lastUri == null) {
            return "ERR:还没有生成文件";
        }
        try {
            Intent i = new Intent(Intent.ACTION_SEND);
            i.setType(DOCX_MIME);
            i.putExtra(Intent.EXTRA_STREAM, lastUri);
            i.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
            startActivity(Intent.createChooser(i, "分享打卡表"));
            return "OK:" + lastWhere;
        } catch (Exception e) {
            return "ERR:" + e;
        }
    }

    /** 用手机上的办公软件打开刚生成的文档 */
    private String open() {
        if (lastUri == null) {
            return "ERR:还没有生成文件";
        }
        try {
            Intent i = new Intent(Intent.ACTION_VIEW);
            i.setDataAndType(lastUri, DOCX_MIME);
            i.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
            // 不套 createChooser：系统设了默认办公软件就直接打开，没设才让用户选
            startActivity(i);
            return "OK:" + lastWhere;
        } catch (Exception e) {
            return "ERR:" + e;
        }
    }

    // ───────── 相册选择回传 ─────────
    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        if (requestCode == REQ_FILE) {
            Uri[] uris = null;
            if (resultCode == RESULT_OK && data != null) {
                if (data.getClipData() != null) {          // 多选
                    int n = data.getClipData().getItemCount();
                    uris = new Uri[n];
                    for (int i = 0; i < n; i++) {
                        uris[i] = data.getClipData().getItemAt(i).getUri();
                    }
                } else if (data.getData() != null) {       // 单选
                    uris = new Uri[]{data.getData()};
                }
            }
            if (fileCallback != null) {
                fileCallback.onReceiveValue(uris);
                fileCallback = null;
            }
            return;
        }
        super.onActivityResult(requestCode, resultCode, data);
    }

    @Override
    public void onBackPressed() {
        if (web != null && web.canGoBack()) {
            web.goBack();
        } else {
            super.onBackPressed();
        }
    }
}
