# fix_indentation.py
with open('blackboard.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Find the misplaced methods (lines 288-324) and remove them
# Then find the LearnAPIVersion class and add them properly indented inside it

# Remove the wrongly placed methods
new_lines = []
skip = False
for i, line in enumerate(lines):
    if i >= 287 and i <= 323:  # Skip lines 288-324 (0-indexed: 287-323)
        skip = True
        continue
    if skip and i > 323:
        skip = False
    if not skip:
        new_lines.append(line)

# Now find LearnAPIVersion __init__ and add methods after it
final_lines = []
for i, line in enumerate(new_lines):
    final_lines.append(line)

    # After the __init__ method ends, add the comparison methods
    if i < len(new_lines) - 1 and 'self._raw = [str(self.major), str(self.minor), str(self.patch)]' in line:
        # Add the methods here with proper indentation
        methods = '''
        def comparable(self) -> tuple:
            """
            Generates a Tuple for version comparison
            :return: Tuple of (major, minor, patch) for comparison
            """
            return (self.major, self.minor, self.patch)

        def __str__(self):
            return "{}.{}.{}".format(self.major, self.minor, self.patch)

        def __lt__(self, other):
            return self.comparable() < other.comparable()

        def __le__(self, other):
            return self.comparable() <= other.comparable()

        def __eq__(self, other):
            return self.comparable() == other.comparable()

        def __ne__(self, other):
            return self.comparable() != other.comparable()

        def __gt__(self, other):
            return self.comparable() > other.comparable()

        def __ge__(self, other):
            return self.comparable() >= other.comparable()

'''
        final_lines.append(methods)

with open('blackboard.py', 'w', encoding='utf-8') as f:
    f.writelines(final_lines)

print("✓ Fixed indentation!")