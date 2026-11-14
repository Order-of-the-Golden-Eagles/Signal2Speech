// Signal2Speech selection contract (issue #22).
// Plain C# with no UnityEngine dependency so it compiles in Unity and in `dotnet test`.
// See docs/architecture/selection-contract.md for the rules these types encode.

using System;
using System.Collections.Generic;

namespace Signal2Speech.Core
{
    /// <summary>Wire values for <see cref="SelectionEvent.source"/>. Label input honestly.</summary>
    public static class InputSources
    {
        public const string Keyboard = "keyboard";
        public const string Simulated = "simulated";
        public const string Recorded = "recorded";
        public const string LiveEeg = "live-eeg";

        public static bool IsKnown(string source) =>
            source == Keyboard || source == Simulated || source == Recorded || source == LiveEeg;
    }

    /// <summary>On-screen target slots. The app maps them to actions per round.</summary>
    public static class TargetIds
    {
        public const string Target1 = "target-1";
        public const string Target2 = "target-2";
    }

    /// <summary>Stable action IDs shared by UI, OpenOrbit, speech, and AI Answering.</summary>
    public static class ActionIds
    {
        // Effects that run only after an explicit confirmation.
        public const string ShowSatellite = "show_satellite";
        public const string CompareAirQuality = "compare_air_quality";
        public const string SpeakReply = "speak_reply";

        // Confirmation-round controls. They never reach an effect sink.
        public const string Confirm = "confirm";
        public const string Cancel = "cancel";
    }

    /// <summary>
    /// The one input shape for keyboard, simulator, recorded, and live EEG.
    /// Lower-case public fields so Unity JsonUtility and System.Text.Json both map it 1:1.
    /// </summary>
    [Serializable]
    public sealed class SelectionEvent
    {
        public string source;
        public string roundId;
        public string eventId;
        public string targetId;

        public SelectionEvent() { }

        public SelectionEvent(string source, string roundId, string eventId, string targetId)
        {
            this.source = source;
            this.roundId = roundId;
            this.eventId = eventId;
            this.targetId = targetId;
        }

        public override string ToString() =>
            $"{{source:{source}, roundId:{roundId}, eventId:{eventId}, targetId:{targetId}}}";
    }

    /// <summary>One visible option. SpokenText is the exact text previewed and later spoken.</summary>
    public sealed class Choice
    {
        public string TargetId { get; }
        public string ActionId { get; }
        public string Label { get; }
        public string SpokenText { get; }

        public Choice(string targetId, string actionId, string label, string spokenText = null)
        {
            TargetId = targetId ?? throw new ArgumentNullException(nameof(targetId));
            ActionId = actionId ?? throw new ArgumentNullException(nameof(actionId));
            Label = label ?? actionId;
            SpokenText = spokenText;
        }
    }

    public enum RoundKind
    {
        /// <summary>Pick a reply or action. A valid pick only previews it.</summary>
        Choose,
        /// <summary>Confirm or Cancel the pending preview.</summary>
        Confirm,
    }

    /// <summary>A frozen set of options. The app issues it; one valid event consumes it.</summary>
    public sealed class Round
    {
        public string Id { get; }
        public RoundKind Kind { get; }
        public IReadOnlyList<Choice> Choices { get; }
        public bool Consumed { get; internal set; }

        internal Round(string id, RoundKind kind, IReadOnlyList<Choice> choices)
        {
            Id = id;
            Kind = kind;
            Choices = choices;
        }

        public Choice Find(string targetId)
        {
            foreach (var c in Choices)
                if (c.TargetId == targetId) return c;
            return null;
        }
    }

    /// <summary>What a confirmed choice asks speech and OpenOrbit to do. Sent exactly once.</summary>
    public sealed class ConfirmedAction
    {
        public string ActionId { get; }
        public string SpokenText { get; }
        public string Source { get; }
        public string PreviewEventId { get; }
        public string ConfirmEventId { get; }

        public ConfirmedAction(string actionId, string spokenText, string source, string previewEventId, string confirmEventId)
        {
            ActionId = actionId;
            SpokenText = spokenText;
            Source = source;
            PreviewEventId = previewEventId;
            ConfirmEventId = confirmEventId;
        }
    }

    /// <summary>Implemented by the output side (#25): OpenOrbit view plus speech.</summary>
    public interface IActionSink
    {
        void Execute(ConfirmedAction action);
    }

    public enum Outcome
    {
        Previewed,
        Confirmed,
        Cancelled,
        RejectedNoOpenRound,
        RejectedStaleRound,
        RejectedDuplicateEvent,
        RejectedRoundConsumed,
        RejectedUnknownTarget,
        RejectedUnknownSource,
        RejectedMalformed,
        RejectedLiveConfirmDisarmed,
    }

    public static class OutcomeExtensions
    {
        public static bool IsRejected(this Outcome o) => o >= Outcome.RejectedNoOpenRound;
    }
}
