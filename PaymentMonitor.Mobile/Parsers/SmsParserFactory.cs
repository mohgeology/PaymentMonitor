using System;
using System.Collections.Generic;
using System.Linq;

namespace PaymentMonitor.Mobile.Parsers;

public class SmsParserFactory
{
    private readonly List<ISmsParser> _parsers = new();

    public static SmsParserFactory Default { get; } = new();

    public SmsParserFactory()
    {
        // Register default wallet parsers
        RegisterParser(new JeebSmsParser());
        RegisterParser(new MobileMoneySmsParser());
        RegisterParser(new AmFlosSmsParser());
    }

    /// <summary>
    /// Registers a new or custom parser without altering existing system architecture.
    /// </summary>
    public void RegisterParser(ISmsParser parser)
    {
        if (parser != null && !_parsers.Contains(parser))
        {
            _parsers.Add(parser);
        }
    }

    public IReadOnlyList<ISmsParser> RegisteredParsers => _parsers.AsReadOnly();

    /// <summary>
    /// Identifies and returns the appropriate parser for the given SMS content and sender.
    /// </summary>
    public ISmsParser? ResolveParser(string message, string? sender = null)
    {
        if (string.IsNullOrWhiteSpace(message))
            return null;

        return _parsers.FirstOrDefault(p => p.CanParse(message, sender));
    }

    /// <summary>
    /// Parses the message using the resolved parser.
    /// </summary>
    public SmsParserResult Parse(string message, string? sender = null)
    {
        if (string.IsNullOrWhiteSpace(message))
            return SmsParserResult.Failed(message ?? string.Empty);

        var parser = ResolveParser(message, sender);
        if (parser != null)
        {
            return parser.Parse(message, sender);
        }

        return SmsParserResult.Failed(message);
    }
}

