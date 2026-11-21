package com.moeen.laibaassistant;

import android.speech.tts.TextToSpeech;
import android.speech.tts.UtteranceProgressListener;

public final class LaibaTtsListener extends UtteranceProgressListener {

    public interface Callback {
        void onStart(String utteranceId);
        void onDone(String utteranceId);
        void onError(String utteranceId, int errorCode);
        void onStop(String utteranceId, boolean interrupted);
    }

    private final Callback callback;

    private LaibaTtsListener(Callback callback) {
        this.callback = callback;
    }

    public static boolean attach(
            TextToSpeech tts,
            Callback callback
    ) {
        if (tts == null || callback == null) {
            return false;
        }

        tts.setOnUtteranceProgressListener(
            new LaibaTtsListener(callback)
        );

        return true;
    }

    @Override
    public void onStart(String utteranceId) {
        try {
            callback.onStart(utteranceId);
        } catch (Exception ignored) {
        }
    }

    @Override
    public void onDone(String utteranceId) {
        try {
            callback.onDone(utteranceId);
        } catch (Exception ignored) {
        }
    }

    @Override
    public void onError(String utteranceId) {
        onError(utteranceId, TextToSpeech.ERROR);
    }

    @Override
    public void onError(String utteranceId, int errorCode) {
        try {
            callback.onError(utteranceId, errorCode);
        } catch (Exception ignored) {
        }
    }

    @Override
    public void onStop(String utteranceId, boolean interrupted) {
        try {
            callback.onStop(utteranceId, interrupted);
        } catch (Exception ignored) {
        }
    }
}
