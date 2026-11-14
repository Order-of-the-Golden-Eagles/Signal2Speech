using System;
using System.Collections.Generic;

namespace Signal2Speech.Core
{
    /// <summary>
    /// The single app-side state machine every input source feeds (issue #22).
    /// Choose round → preview → fresh Confirm round → exactly one effect.
    /// Not thread-safe: call from the Unity main thread (marshal vendor callbacks first).
    /// </summary>
    public sealed class SelectionHandler
    {
        private readonly IActionSink _sink;
        private readonly HashSet<string> _seenEventIds = new HashSet<string>();
        private int _roundCounter;
        private Choice _pending;
        private string _pendingEventId;

        public SelectionHandler(IActionSink sink)
        {
            _sink = sink ?? throw new ArgumentNullException(nameof(sink));
        }

        /// <summary>The open round, or null between rounds.</summary>
        public Round Current { get; private set; }

        /// <summary>The previewed choice awaiting Confirm, or null.</summary>
        public Choice Pending => _pending;

        /// <summary>
        /// Live EEG may preview, but may not confirm, until #23 proves callbacks cannot cross rounds.
        /// Keyboard, simulated, and recorded input can always confirm.
        /// </summary>
        public bool LiveEegConfirmArmed { get; set; }

        /// <summary>Raised when a round opens. UI renders its choices; adapters stamp its Id at capture.</summary>
        public event Action<Round> RoundOpened;

        /// <summary>Raised when a choice is previewed. UI shows exact text plus Confirm/Cancel. No effects.</summary>
        public event Action<Choice> PreviewShown;

        /// <summary>Raised when a round closes without an effect (cancel, reset, disconnect).</summary>
        public event Action<string> Cleared;

        /// <summary>Raised for every handled event, accepted or not. Use for logs and the judge view.</summary>
        public event Action<SelectionEvent, Outcome> Handled;

        /// <summary>Opens a Choose round with frozen options. Closes any open round and clears any preview.</summary>
        public Round BeginChoiceRound(IReadOnlyList<Choice> choices)
        {
            if (choices == null || choices.Count == 0) throw new ArgumentException("A round needs choices.", nameof(choices));
            foreach (var c in choices)
                if (c.ActionId == ActionIds.Confirm || c.ActionId == ActionIds.Cancel)
                    throw new ArgumentException("Confirm/Cancel belong to confirmation rounds only.", nameof(choices));
            _pending = null;
            _pendingEventId = null;
            return Open(RoundKind.Choose, new List<Choice>(choices));
        }

        /// <summary>Applies one event. Returns the outcome; side effects happen only on Confirmed.</summary>
        public Outcome Handle(SelectionEvent e)
        {
            var outcome = Apply(e);
            Handled?.Invoke(e, outcome);
            return outcome;
        }

        /// <summary>Wearer-independent cancel (judge button, Esc). Clears preview, no effect.</summary>
        public void Cancel(string reason = "cancel") => Close(reason);

        /// <summary>Headset or bridge dropped. Clears preview, no effect.</summary>
        public void Disconnect(string reason = "disconnect") => Close(reason);

        private Outcome Apply(SelectionEvent e)
        {
            if (e == null || string.IsNullOrEmpty(e.roundId) || string.IsNullOrEmpty(e.eventId) || string.IsNullOrEmpty(e.targetId))
                return Outcome.RejectedMalformed;
            if (!InputSources.IsKnown(e.source)) return Outcome.RejectedUnknownSource;
            if (Current == null) return Outcome.RejectedNoOpenRound;
            if (e.roundId != Current.Id) return Outcome.RejectedStaleRound;
            if (_seenEventIds.Contains(e.eventId)) return Outcome.RejectedDuplicateEvent;
            if (Current.Consumed) return Outcome.RejectedRoundConsumed;

            var choice = Current.Find(e.targetId);
            if (choice == null) return Outcome.RejectedUnknownTarget;

            if (Current.Kind == RoundKind.Confirm && choice.ActionId == ActionIds.Confirm
                && e.source == InputSources.LiveEeg && !LiveEegConfirmArmed)
                return Outcome.RejectedLiveConfirmDisarmed; // round stays open for keyboard/simulated confirm

            // Consume before any UI update or effect so a repeated callback cannot run twice.
            _seenEventIds.Add(e.eventId);
            Current.Consumed = true;

            if (Current.Kind == RoundKind.Choose)
            {
                _pending = choice;
                _pendingEventId = e.eventId;
                PreviewShown?.Invoke(choice);
                Open(RoundKind.Confirm, new List<Choice>
                {
                    new Choice(TargetIds.Target1, ActionIds.Confirm, "Confirm"),
                    new Choice(TargetIds.Target2, ActionIds.Cancel, "Cancel"),
                });
                return Outcome.Previewed;
            }

            if (choice.ActionId == ActionIds.Cancel)
            {
                Close("cancel");
                return Outcome.Cancelled;
            }

            var pending = _pending;
            var previewId = _pendingEventId;
            _pending = null;
            _pendingEventId = null;
            Current = null;
            _sink.Execute(new ConfirmedAction(pending.ActionId, pending.SpokenText, e.source, previewId, e.eventId));
            return Outcome.Confirmed;
        }

        private Round Open(RoundKind kind, IReadOnlyList<Choice> choices)
        {
            _roundCounter++;
            Current = new Round("r" + _roundCounter, kind, choices);
            RoundOpened?.Invoke(Current);
            return Current;
        }

        private void Close(string reason)
        {
            var hadSomething = Current != null || _pending != null;
            if (Current != null) Current.Consumed = true;
            Current = null;
            _pending = null;
            _pendingEventId = null;
            if (hadSomething) Cleared?.Invoke(reason);
        }
    }
}
