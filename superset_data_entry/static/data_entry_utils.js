/**
 * Shared frontend utilities for the Data Entry Plugin.
 *
 * Exposes `window.DataEntryUtils` with:
 *   getCsrfToken()          – reads the CSRF token from <meta name="csrf-token">
 *   showToast(msg, type)    – shows a dismissible Bootstrap-style alert
 *   confirmAction(msg, fn)  – shows a modal confirmation dialog
 */
(function (window) {
    'use strict';

    // ── CSRF ──────────────────────────────────────────────────────────────────

    function getCsrfToken() {
        var meta = document.querySelector('meta[name="csrf-token"]');
        return meta ? meta.content : '';
    }

    // ── Toast notifications ───────────────────────────────────────────────────

    /**
     * @param {string} message   Text to show (HTML-escaped automatically).
     * @param {string} [type]    Bootstrap alert type: success | danger | warning | info
     * @param {number} [duration] Auto-dismiss after ms (default 5000; 0 = never)
     */
    function showToast(message, type, duration) {
        type     = type     || 'info';
        duration = (duration === undefined) ? 5000 : duration;

        var container = document.getElementById('deToastContainer');
        if (!container) {
            container = document.createElement('div');
            container.id = 'deToastContainer';
            container.setAttribute(
                'style',
                'position:fixed;top:1rem;right:1rem;z-index:9999;' +
                'min-width:280px;max-width:420px;pointer-events:auto;'
            );
            document.body.appendChild(container);
        }

        var safeMsg = String(message)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;');

        var toast = document.createElement('div');
        toast.className = 'alert alert-' + type + ' mb-2';
        toast.setAttribute(
            'style',
            'box-shadow:0 2px 8px rgba(0,0,0,.2);' +
            'display:flex;align-items:flex-start;gap:.5rem;'
        );
        toast.innerHTML =
            '<span style="flex:1;">' + safeMsg + '</span>' +
            '<button type="button" ' +
            'style="background:none;border:none;font-size:1.2rem;line-height:1;' +
            'cursor:pointer;padding:0;" ' +
            'onclick="this.parentElement.remove()">&times;</button>';

        container.appendChild(toast);

        if (duration > 0) {
            setTimeout(function () {
                if (toast.parentNode) { toast.remove(); }
            }, duration);
        }
    }

    // ── Confirm dialog ────────────────────────────────────────────────────────

    /**
     * @param {string}   message        Question to show (HTML-escaped).
     * @param {Function} onConfirm      Called when the user clicks confirm.
     * @param {string}   [confirmLabel] Button label (default 'Confirm').
     * @param {string}   [confirmClass] Bootstrap btn class (default 'btn-danger').
     */
    function confirmAction(message, onConfirm, confirmLabel, confirmClass) {
        confirmLabel = confirmLabel || 'Confirm';
        confirmClass = confirmClass || 'btn-danger';

        var safeMsg = String(message)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;');

        var overlay = document.createElement('div');
        overlay.setAttribute(
            'style',
            'position:fixed;inset:0;background:rgba(0,0,0,.45);z-index:10000;' +
            'display:flex;align-items:center;justify-content:center;'
        );

        var dialog = document.createElement('div');
        dialog.setAttribute(
            'style',
            'background:#fff;border-radius:6px;padding:1.5rem;' +
            'max-width:400px;width:90%;box-shadow:0 4px 20px rgba(0,0,0,.3);'
        );
        dialog.innerHTML =
            '<p style="margin-bottom:1.25rem;">' + safeMsg + '</p>' +
            '<div style="text-align:right;display:flex;gap:.5rem;justify-content:flex-end;">' +
            '<button id="deConfirmCancel" class="btn btn-secondary btn-sm">Cancel</button>' +
            '<button id="deConfirmOk" class="btn ' + confirmClass + ' btn-sm">' +
            confirmLabel + '</button>' +
            '</div>';

        overlay.appendChild(dialog);
        document.body.appendChild(overlay);

        function close() { overlay.remove(); }
        document.getElementById('deConfirmCancel').onclick = close;
        document.getElementById('deConfirmOk').onclick = function () {
            close();
            onConfirm();
        };
        overlay.onclick = function (e) { if (e.target === overlay) { close(); } };
    }

    // ── Public API ────────────────────────────────────────────────────────────

    window.DataEntryUtils = {
        getCsrfToken:  getCsrfToken,
        showToast:     showToast,
        confirmAction: confirmAction
    };

}(window));
