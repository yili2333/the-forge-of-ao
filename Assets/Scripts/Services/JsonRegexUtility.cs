using System;
using System.Collections.Generic;
using System.Globalization;
using System.Text.RegularExpressions;

public static class JsonRegexUtility
{
    public static string ExtractString(string json, string key)
    {
        if (string.IsNullOrWhiteSpace(json) || string.IsNullOrWhiteSpace(key))
        {
            return string.Empty;
        }

        string pattern = "\"" + Regex.Escape(key) + "\"\\s*:\\s*\"(?<value>(?:\\\\.|[^\"])*)\"";
        Match match = Regex.Match(json, pattern, RegexOptions.IgnoreCase | RegexOptions.Singleline);
        if (!match.Success)
        {
            return string.Empty;
        }

        return Regex.Unescape(match.Groups["value"].Value ?? string.Empty);
    }

    public static bool? ExtractBool(string json, string key)
    {
        string pattern = "\"" + Regex.Escape(key) + "\"\\s*:\\s*(true|false)";
        Match match = Regex.Match(json ?? string.Empty, pattern, RegexOptions.IgnoreCase);
        if (!match.Success)
        {
            return null;
        }

        return match.Groups[1].Value.ToLowerInvariant() == "true";
    }

    public static int? ExtractInt(string json, string key)
    {
        string pattern = "\"" + Regex.Escape(key) + "\"\\s*:\\s*(-?\\d+)";
        Match match = Regex.Match(json ?? string.Empty, pattern, RegexOptions.IgnoreCase);
        if (!match.Success)
        {
            return null;
        }

        int value;
        return int.TryParse(match.Groups[1].Value, NumberStyles.Integer, CultureInfo.InvariantCulture, out value) ? value : (int?)null;
    }

    public static float? ExtractFloat(string json, string key)
    {
        string pattern = "\"" + Regex.Escape(key) + "\"\\s*:\\s*(-?\\d+(?:\\.\\d+)?)";
        Match match = Regex.Match(json ?? string.Empty, pattern, RegexOptions.IgnoreCase);
        if (!match.Success)
        {
            return null;
        }

        float value;
        return float.TryParse(match.Groups[1].Value, NumberStyles.Float, CultureInfo.InvariantCulture, out value) ? value : (float?)null;
    }

    public static string ExtractObject(string json, string key)
    {
        return ExtractStructuredValue(json, key, '{', '}');
    }

    public static string ExtractArray(string json, string key)
    {
        return ExtractStructuredValue(json, key, '[', ']');
    }

    public static List<string> SplitTopLevelObjects(string jsonArray)
    {
        return SplitTopLevelStructured(jsonArray, '{', '}');
    }

    public static List<string> SplitTopLevelArrays(string jsonArray)
    {
        return SplitTopLevelStructured(jsonArray, '[', ']');
    }

    public static List<string> ExtractStringArray(string json, string key)
    {
        string arrayJson = ExtractArray(json, key);
        if (string.IsNullOrWhiteSpace(arrayJson))
        {
            return new List<string>();
        }

        List<string> values = new List<string>();
        bool inString = false;
        bool escape = false;
        int start = -1;

        for (int i = 0; i < arrayJson.Length; i++)
        {
            char ch = arrayJson[i];
            if (!inString)
            {
                if (ch == '"')
                {
                    inString = true;
                    start = i + 1;
                }
                continue;
            }

            if (escape)
            {
                escape = false;
                continue;
            }

            if (ch == '\\')
            {
                escape = true;
                continue;
            }

            if (ch == '"')
            {
                values.Add(Regex.Unescape(arrayJson.Substring(start, i - start)));
                inString = false;
                start = -1;
            }
        }

        return values;
    }

    public static List<KeyValuePair<string, string>> ExtractTopLevelObjectEntries(string jsonObject)
    {
        List<KeyValuePair<string, string>> entries = new List<KeyValuePair<string, string>>();
        if (string.IsNullOrWhiteSpace(jsonObject))
        {
            return entries;
        }

        int index = 0;
        while (index < jsonObject.Length && char.IsWhiteSpace(jsonObject[index])) index++;
        if (index >= jsonObject.Length || jsonObject[index] != '{') return entries;
        index++;

        while (index < jsonObject.Length)
        {
            while (index < jsonObject.Length && (char.IsWhiteSpace(jsonObject[index]) || jsonObject[index] == ',')) index++;
            if (index >= jsonObject.Length || jsonObject[index] == '}') break;
            if (jsonObject[index] != '"') break;

            int keyStart = ++index;
            bool escape = false;
            while (index < jsonObject.Length)
            {
                char ch = jsonObject[index];
                if (escape)
                {
                    escape = false;
                }
                else if (ch == '\\')
                {
                    escape = true;
                }
                else if (ch == '"')
                {
                    break;
                }
                index++;
            }

            if (index >= jsonObject.Length) break;
            string key = Regex.Unescape(jsonObject.Substring(keyStart, index - keyStart));
            index++;
            while (index < jsonObject.Length && (char.IsWhiteSpace(jsonObject[index]) || jsonObject[index] == ':')) index++;
            if (index >= jsonObject.Length) break;

            int valueStart = index;
            string value;
            if (jsonObject[index] == '{')
            {
                value = ExtractStructuredAt(jsonObject, index, '{', '}');
                index = valueStart + value.Length;
            }
            else if (jsonObject[index] == '[')
            {
                value = ExtractStructuredAt(jsonObject, index, '[', ']');
                index = valueStart + value.Length;
            }
            else if (jsonObject[index] == '"')
            {
                index++;
                bool valueEscape = false;
                while (index < jsonObject.Length)
                {
                    char ch = jsonObject[index];
                    if (valueEscape)
                    {
                        valueEscape = false;
                    }
                    else if (ch == '\\')
                    {
                        valueEscape = true;
                    }
                    else if (ch == '"')
                    {
                        break;
                    }
                    index++;
                }
                value = index < jsonObject.Length ? jsonObject.Substring(valueStart, index - valueStart + 1) : jsonObject.Substring(valueStart);
                index++;
            }
            else
            {
                while (index < jsonObject.Length && jsonObject[index] != ',' && jsonObject[index] != '}') index++;
                value = jsonObject.Substring(valueStart, index - valueStart).Trim();
            }

            entries.Add(new KeyValuePair<string, string>(key, value));
        }

        return entries;
    }

    private static string ExtractStructuredValue(string json, string key, char openChar, char closeChar)
    {
        if (string.IsNullOrWhiteSpace(json) || string.IsNullOrWhiteSpace(key))
        {
            return string.Empty;
        }

        Match match = Regex.Match(json, "\"" + Regex.Escape(key) + "\"\\s*:", RegexOptions.IgnoreCase | RegexOptions.Singleline);
        if (!match.Success)
        {
            return string.Empty;
        }

        int index = match.Index + match.Length;
        while (index < json.Length && char.IsWhiteSpace(json[index])) index++;
        if (index >= json.Length || json[index] != openChar)
        {
            return string.Empty;
        }

        return ExtractStructuredAt(json, index, openChar, closeChar);
    }

    private static string ExtractStructuredAt(string json, int startIndex, char openChar, char closeChar)
    {
        int depth = 0;
        bool inString = false;
        bool escape = false;

        for (int i = startIndex; i < json.Length; i++)
        {
            char ch = json[i];
            if (inString)
            {
                if (escape)
                {
                    escape = false;
                }
                else if (ch == '\\')
                {
                    escape = true;
                }
                else if (ch == '"')
                {
                    inString = false;
                }
                continue;
            }

            if (ch == '"')
            {
                inString = true;
                continue;
            }

            if (ch == openChar)
            {
                depth++;
            }
            else if (ch == closeChar)
            {
                depth--;
                if (depth == 0)
                {
                    return json.Substring(startIndex, i - startIndex + 1);
                }
            }
        }

        return string.Empty;
    }

    private static List<string> SplitTopLevelStructured(string jsonArray, char openChar, char closeChar)
    {
        List<string> items = new List<string>();
        if (string.IsNullOrWhiteSpace(jsonArray))
        {
            return items;
        }

        int startIndex = -1;
        int depth = 0;
        bool inString = false;
        bool escape = false;

        for (int i = 0; i < jsonArray.Length; i++)
        {
            char ch = jsonArray[i];
            if (inString)
            {
                if (escape)
                {
                    escape = false;
                }
                else if (ch == '\\')
                {
                    escape = true;
                }
                else if (ch == '"')
                {
                    inString = false;
                }
                continue;
            }

            if (ch == '"')
            {
                inString = true;
                continue;
            }

            if (ch == openChar)
            {
                if (depth == 0)
                {
                    startIndex = i;
                }
                depth++;
            }
            else if (ch == closeChar)
            {
                depth--;
                if (depth == 0 && startIndex >= 0)
                {
                    items.Add(jsonArray.Substring(startIndex, i - startIndex + 1));
                    startIndex = -1;
                }
            }
        }

        return items;
    }
}
