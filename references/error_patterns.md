# Error Patterns Reference

Common API errors and their handling strategies.

## Retryable Errors (Trigger Key Rotation)

### Rate Limit (429)
**Pattern:** `rate limit`, `429`, `too many requests`, `tpm`, `rpm`

**Response:**
- Mark key as cooling down (60 seconds)
- Rotate to next key immediately
- Retry request with new key

**Example Messages:**
```
Rate limit exceeded (429)
Tokens per minute limit reached
Requests per minute limit exceeded
```

### Timeout (408/504)
**Pattern:** `timeout`, `408`, `504`, `gateway timeout`

**Response:**
- Retry same key once after 2-second delay
- If still failing, mark cooldown and rotate

**Example Messages:**
```
Request timeout (408)
Gateway timeout (504)
Connection timeout
```

### Connection Errors
**Pattern:** `connection`, `reset`, `refused`, `network`

**Response:**
- Wait 3 seconds
- Rotate to next key

**Example Messages:**
```
Connection error
Connection reset by peer
Unable to connect
```

### Context Length
**Pattern:** `context_length_exceeded`, `maximum context length`

**Response:**
- Trigger context compaction
- Remove oldest messages or summarize
- Retry with same key (compaction fixes the issue)

## Non-Retryable Errors (Fail Immediately)

### Authentication (401/403)
**Pattern:** `invalid_api_key`, `authentication`, `401`, `403`, `unauthorized`

**Response:**
- Do NOT rotate keys
- Fail immediately
- Log error for investigation

**Example Messages:**
```
Invalid API key (401)
Authentication failed
Unauthorized
```

### Bad Request (400)
**Pattern:** `invalid_request`, `bad request`, `400`

**Response:**
- Do NOT retry
- Return error to caller

**Example Messages:**
```
Invalid request format
Bad request
Malformed request
```

### Model Not Found (404)
**Pattern:** `model_not_found`, `not_found`, `404`

**Response:**
- Fail immediately
- Check model name configuration

## NVIDIA-Specific Errors

### NVCF Errors
NVIDIA Cloud Functions may return:
- `NVCF-REQ-001`: Request error (retryable)
- `NVCF-REQ-002`: Rate limit (retryable with rotation)
- `NVCF-AUTH-001`: Auth error (non-retryable)

### Inference Errors
- `inference_timeout`: Retry with rotation
- `model_loading`: Wait 5s, retry same key
- `insufficient_quota`: Rotate immediately

## Error Detection Logic

```python
def is_retryable_error(error):
    error_str = str(error).lower()

    retryable_patterns = [
        'rate_limit', 'rate limit', '429',
        'timeout', '408', '504',
        'connection', 'reset',
        'context_length_exceeded',
        'tokens per minute', 'tpm', 'rpm',
        'too many requests'
    ]

    for pattern in retryable_patterns:
        if pattern in error_str:
            return True

    # Check status codes
    if any(code in error_str for code in ['429', '408', '504']):
        return True

    return False
```

## Retry Strategy Matrix

| Error Type | Retry Same Key | Rotate Key | Delay |
|------------|----------------|------------|-------|
| Rate Limit (429) | No | Yes | Immediate |
| Timeout (408) | Yes (1x) | Yes (if retry fails) | 2s |
| Connection | No | Yes | 3s |
| Context Length | Yes (after compaction) | No | 0s |
| Auth Error | No | No | N/A |
| Bad Request | No | No | N/A |
