import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock

# Assuming AppState and Config can be instantiated simply for this test
# If they have complex dependencies, these might need to be mocked more thoroughly
from state_models import AppState
from config import Config # Assuming Config can be imported and instantiated
from llm_interface import LLMInterface # Make sure this path is correct

# Dummy parts for testing
class DummyPart:
    def __init__(self, text=None, function_call_obj=None, is_malformed_fc=False):
        self.text = text
        self._is_malformed_fc = is_malformed_fc
        if function_call_obj:
            # Simulate the structure of a function call part
            self.function_call = function_call_obj
        elif is_malformed_fc:
            # This part will simulate the problematic access
            # It has 'function_call' but accessing it raises an error
            # or returns something that causes an issue in SDK if not checked by _raw
            pass # No actual function_call attribute to prevent easy hasattr check bypass
        
        # Simulate the _raw attribute behavior
        if function_call_obj:
            self._raw = MagicMock()
            self._raw.WhichOneof.return_value = "function_call"
        elif is_malformed_fc: # A part that looks like it *might* be an FC but isn't, or is broken
            self._raw = MagicMock()
            self._raw.WhichOneof.return_value = "text" # Or some other non-FC type that would cause issues if .function_call is accessed
            # To simulate the crash, we can make .function_call raise an error when accessed
            # The property trick is a good way to do this.
            _fc_val = None # Placeholder
            def _get_fc():
                raise TypeError("Simulated SDK error: Could not convert `part.function_call` to text")
            def _set_fc(val):
                nonlocal _fc_val
                _fc_val = val
            # This part *has* function_call, but accessing it blows up
            # This is what the original code was trying to guard against more robustly
            # For testing the _raw path, this part will have _raw indicating not a function_call
            # and also have a function_call attribute that would explode.
            # The _raw check should prevent the explosion.
            # Let's name it to reflect it might explode if not for _raw
            self.function_call = property(_get_fc, _set_fc)

        elif text is not None:
            self._raw = MagicMock()
            self._raw.WhichOneof.return_value = "text"
        else: # A part that has neither text nor a valid FC, maybe an empty part
            self._raw = MagicMock()
            self._raw.WhichOneof.return_value = "none" # Or some other type


class DummyCandidate:
    def __init__(self, parts):
        self.content = MagicMock()
        self.content.parts = parts

class DummyResponse:
    def __init__(self, candidates):
        self.candidates = candidates
        self.text = None # For parts that are directly text
        self.parts = [] # For parts that are directly parts (if stream yields response objects directly)

@pytest.fixture
def config_instance():
    """Provides a Config instance for tests."""
    # This might need more setup if Config has required args or complex init
    return Config()

@pytest.fixture
def app_state_instance():
    """Provides an AppState instance for tests."""
    # This might need more setup
    return AppState()

@pytest.fixture
def dummy_part_text():
    return DummyPart(text="Hello, world!")

@pytest.fixture
def dummy_part_function_call():
    fc_data = MagicMock()
    fc_data.name = "test_function"
    fc_data.args = {"arg1": "value1"}
    return DummyPart(function_call_obj=fc_data)

@pytest.fixture
def dummy_part_malformed_fc_explodes_on_access():
    # This part has _raw indicating it's NOT a function call,
    # but also has a .function_call property that would raise an error if accessed.
    # The goal is for the _raw check to prevent the access to .function_call.
    part = DummyPart(is_malformed_fc=True) # is_malformed_fc sets up _raw and problematic .function_call
    part._raw.WhichOneof.return_value = "text" # Explicitly not 'function_call'
    
    # Ensure accessing .function_call would raise an error
    _fc_val = None 
    def _get_fc():
        raise TypeError("Simulated SDK error: Could not convert `part.function_call` to text")
    def _set_fc(val):
        nonlocal _fc_val
        _fc_val = val
    part.function_call = property(_get_fc, _set_fc)
    return part


@pytest.fixture
def dummy_part_looks_like_fc_but_isnt_via_raw():
    # This part might have a function_call attribute, but _raw says it is not a function_call
    part = DummyPart(text="This is actually text, but might have an fc attr.")
    part._raw = MagicMock()
    part._raw.WhichOneof.return_value = "text" # Key: _raw says it's text
    
    # It might even have a (dormant) function_call attribute
    # fc_data = MagicMock()
    # fc_data.name = "some_other_function"
    # fc_data.args = {}
    # part.function_call = fc_data 
    # For this test, let's assume it doesn't have a problematic fc, _raw is the guard
    return part


@pytest.mark.asyncio
async def test_stream_handles_text_and_fc_parts_gracefully(
    config_instance, app_state_instance, 
    dummy_part_text, dummy_part_function_call
):
    """Test that the stream processes both text and valid function calls correctly."""
    llm_interface = LLMInterface(config_instance)
    
    # Simulate the model's generate_content method returning an async iterator
    # The stream yields response objects, which have candidates, which have parts
    mock_response_stream = [
        DummyResponse(candidates=[DummyCandidate(parts=[dummy_part_text])]),
        DummyResponse(candidates=[DummyCandidate(parts=[dummy_part_function_call])])
    ]
    
    llm_interface.model = MagicMock() # Mock the model attribute
    llm_interface.model.generate_content = AsyncMock(return_value=iter(mock_response_stream))
    
    # Mock messages for the stream
    messages = [{"role": "user", "parts": [{"text": "Test query"}]}]
    
    chunks = []
    async for chunk in llm_interface.generate_content_stream(messages=messages, app_state=app_state_instance):
        chunks.append(chunk)
        
    assert any(c.get("type") == "text_chunk" and c.get("content") == "Hello, world!" for c in chunks), "Text chunk not found or incorrect"
    assert any(c.get("type") == "tool_calls" and c["content"][0]["function"]["name"] == "test_function" for c in chunks), "Function call chunk not found or incorrect"
    assert any(c.get("type") == "completed" for c in chunks), "Stream did not complete successfully"
    assert not any(c.get("type") == "error" for c in chunks), "Stream produced an error"

@pytest.mark.asyncio
async def test_stream_survives_malformed_fc_if_raw_prevents_access(
    config_instance, app_state_instance, 
    dummy_part_text, dummy_part_malformed_fc_explodes_on_access
):
    """
    Test that if _raw indicates a part is not a function call,
    the problematic .function_call attribute is never accessed,
    even if present and faulty. The text part should still be processed.
    """
    llm_interface = LLMInterface(config_instance)
    
    mock_response_stream = [
        # This part has _raw indicating text, and a .function_call that would explode.
        # The _raw check should mean .function_call is never touched.
        DummyResponse(candidates=[DummyCandidate(parts=[dummy_part_malformed_fc_explodes_on_access])]),
        # This part is normal text.
        DummyResponse(candidates=[DummyCandidate(parts=[dummy_part_text])]) 
    ]
    
    llm_interface.model = MagicMock()
    llm_interface.model.generate_content = AsyncMock(return_value=iter(mock_response_stream))
    messages = [{"role": "user", "parts": [{"text": "Test query for malformed part"}]}]
    
    chunks = []
    async for chunk in llm_interface.generate_content_stream(messages=messages, app_state=app_state_instance):
        chunks.append(chunk)
        
    # Since dummy_part_malformed_fc_explodes_on_access has _raw indicating "text" (even if its text is None)
    # and its .function_call would explode, the _raw check should prevent the explosion.
    # The part might not yield text if its .text is None, but it should NOT error.
    # The second part (dummy_part_text) should yield text.
    
    assert any(c.get("type") == "text_chunk" and c.get("content") == "Hello, world!" for c in chunks), "Expected text chunk not found"
    assert any(c.get("type") == "completed" for c in chunks), "Stream did not complete successfully"
    assert not any(c.get("type") == "error" for c in chunks), "Stream produced an error, indicating problematic .function_call was likely accessed"

@pytest.mark.asyncio
async def test_stream_handles_part_identified_as_non_fc_by_raw_correctly(
    config_instance, app_state_instance, 
    dummy_part_looks_like_fc_but_isnt_via_raw, dummy_part_text
):
    """
    Test that a part which _raw identifies as not a function_call,
    is treated as text (if it has text) and does not attempt FC processing,
    even if it coincidentally has a 'function_call' attribute.
    """
    llm_interface = LLMInterface(config_instance)
    
    mock_response_stream = [
        DummyResponse(candidates=[DummyCandidate(parts=[dummy_part_looks_like_fc_but_isnt_via_raw])]),
        DummyResponse(candidates=[DummyCandidate(parts=[dummy_part_text])])
    ]
    
    llm_interface.model = MagicMock()
    llm_interface.model.generate_content = AsyncMock(return_value=iter(mock_response_stream))
    messages = [{"role": "user", "parts": [{"text": "Test query"}]}]
    
    chunks = []
    async for chunk in llm_interface.generate_content_stream(messages=messages, app_state=app_state_instance):
        chunks.append(chunk)
        
    # dummy_part_looks_like_fc_but_isnt_via_raw should be processed as text
    expected_text1 = dummy_part_looks_like_fc_but_isnt_via_raw.text
    assert any(c.get("type") == "text_chunk" and c.get("content") == expected_text1 for c in chunks), f"Text chunk for part '{expected_text1}' not found"
    assert any(c.get("type") == "text_chunk" and c.get("content") == "Hello, world!" for c in chunks), "Second text chunk not found"
    
    assert not any(c.get("type") == "tool_calls" for c in chunks), "Tool call was unexpectedly processed"
    assert any(c.get("type") == "completed" for c in chunks), "Stream did not complete successfully"
    assert not any(c.get("type") == "error" for c in chunks), "Stream produced an error"

# Your original test case, adapted slightly
@pytest.mark.asyncio
async def test_stream_without_function_call_crash_original_logic(config_instance, app_state_instance, dummy_part_text, dummy_part_malformed_fc_explodes_on_access):
    """This is closer to the user's provided test.
    dummy_part_malformed_fc_explodes_on_access will be the 'other' part.
    The key is that its ._raw.WhichOneof("data") != "function_call" should prevent
    the part_item.function_call access that would explode.
    """
    llm_interface = LLMInterface(config_instance)

    # This part will make .function_call explode if accessed
    exploding_part = dummy_part_malformed_fc_explodes_on_access 
    # Crucially, its _raw attribute must indicate it's not a function call
    # The fixture dummy_part_malformed_fc_explodes_on_access already sets _raw.WhichOneof to "text"

    mock_response_stream = [
        DummyResponse(candidates=[DummyCandidate(parts=[dummy_part_text])]),
        DummyResponse(candidates=[DummyCandidate(parts=[exploding_part])]) 
    ]
    
    llm_interface.model = MagicMock()
    llm_interface.model.generate_content = AsyncMock(return_value=iter(mock_response_stream))
    
    messages = [{"role": "user", "parts": [{"text": "Test query"}]}]
    
    chunks = []
    async for chunk in llm_interface.generate_content_stream(messages=messages, app_state=app_state_instance):
        chunks.append(chunk)
        
    assert any(c.get("type") == "completed" for c in chunks)
    assert not any(c.get("type") == "error" for c in chunks)
    # Also assert that the text from dummy_part_text was received
    assert any(c.get("type") == "text_chunk" and c.get("content") == "Hello, world!" for c in chunks)


</rewritten_file> 