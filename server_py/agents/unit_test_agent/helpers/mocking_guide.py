def get_mocking_guidance(language: str) -> str:
    if language == "python":
        return "4. Use unittest.mock.patch, unittest.mock.MagicMock, or pytest-mock (mocker fixture) for mocking"
    elif language in ("javascript", "typescript"):
        return "4. Use jest.mock() for module mocking, jest.fn() for function mocking, and jest.spyOn() for method spying"
    elif language == "go":
        return "4. Use interfaces and dependency injection for mocking; create mock structs that implement the required interfaces"
    elif language == "java":
        return "4. Use Mockito (@Mock, @InjectMocks, when().thenReturn()) for mocking dependencies"
    else:
        return "4. Use the standard mocking library for this language to mock all external dependencies"
