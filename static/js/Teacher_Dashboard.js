// Dynamic Calendar (the right panel uses this)
let currentMonth;
let currentYear;
const todayDate = new Date();
document.addEventListener("DOMContentLoaded", function () {
  const today = new Date();
  currentMonth = today.getMonth();
  currentYear = today.getFullYear();
  updateCalendar(currentMonth, currentYear);
  document.getElementById("prevMonth").addEventListener("click", () => {
    currentMonth--;
    if (currentMonth < 0) {
      currentMonth = 11;
      currentYear--;
    }
    updateCalendar(currentMonth, currentYear);
  });
  document.getElementById("nextMonth").addEventListener("click", () => {
    currentMonth++;
    if (currentMonth > 11) {
      currentMonth = 0;
      currentYear++;
    }
    updateCalendar(currentMonth, currentYear);
  });
});
function updateCalendar(month, year) {
  const monthNames = ["January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December"];
  document.getElementById("monthYear").textContent = monthNames[month] + " " + year;
  document.getElementById("calendarContainer").innerHTML = generateCalendar(month, year);
}
function generateCalendar(month, year) {
  const daysInMonth = new Date(year, month + 1, 0).getDate();
  const firstDay   = new Date(year, month, 1).getDay();
  const dayNames   = ["Sun","Mon","Tue","Wed","Thu","Fri","Sat"];
  let table = "<table><thead><tr>";
  dayNames.forEach(d => table += `<th>${d}</th>`);
  table += `</tr></thead><tbody>`;

  let date = 1;
  for (let row = 0; row < 6; row++) {
    table += "<tr>";
    for (let col = 0; col < 7; col++) {
      if (row === 0 && col < firstDay) {
        table += "<td></td>";
      } else if (date > daysInMonth) {
        table += "<td></td>";
      } else {
        // check if this cell is today
        const isToday = 
          date === todayDate.getDate() &&
          month === todayDate.getMonth() &&
          year  === todayDate.getFullYear();

        table += `<td${isToday ? ' class="today"' : ''}>${date}</td>`;
        date++;
      }
    }
    table += "</tr>";
    if (date > daysInMonth) break;
  }
  table += "</tbody></table>";
  return table;
}

  

//   .....................................
document.addEventListener("DOMContentLoaded", () => {
    const subjectTable = document.querySelector("#subjectTable tbody");
    const addSubjectBtn = document.querySelector("#addSubject");
    const totalPercentageInput = document.querySelector("#total-percentage");

    // Function to update subject-wise percentage
    function updatePercentage() {
        let totalMarks = 0;
        let subjectCount = 0;
        
        document.querySelectorAll(".marks-input").forEach((input, index) => {
            const marks = parseFloat(input.value) || 0;
            totalMarks += marks;
            subjectCount++;

            const percentageCell = document.querySelectorAll(".percentage")[index];
            percentageCell.textContent = marks + "%";
        });

        // Calculate total percentage
        if (subjectCount > 0) {
            const overallPercentage = (totalMarks / subjectCount).toFixed(2);
            totalPercentageInput.value = overallPercentage + "%";
        } else {
            totalPercentageInput.value = "0%";
        }
    }

    // Add New Subject Row
    addSubjectBtn.addEventListener("click", () => {
        const newRow = document.createElement("tr");
        newRow.innerHTML = `
            <td><input type="text" placeholder="Enter subject" required></td>
            <td><input type="number" class="marks-input" min="0" max="100" placeholder="Marks" required></td>
            <td class="percentage">0%</td>
            <td><button type="button" class="remove-btn">Remove</button></td>
        `;
        subjectTable.appendChild(newRow);

        // Attach event listener for live percentage updates
        newRow.querySelector(".marks-input").addEventListener("input", updatePercentage);
    });

    // Remove Subject Row
    subjectTable.addEventListener("click", (event) => {
        if (event.target.classList.contains("remove-btn")) {
            event.target.closest("tr").remove();
            updatePercentage();
        }
    });

    // Update percentage on input
    document.querySelectorAll(".marks-input").forEach(input => {
        input.addEventListener("input", updatePercentage);
    });

    // Submit Form
    document.querySelector("#reportForm").addEventListener("submit", (event) => {
        event.preventDefault();
        alert("Report Submitted Successfully!");
    });
});


// ............................................
